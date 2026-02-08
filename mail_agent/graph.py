"""LangGraph pipeline for the Mail Agent."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, TypedDict, TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError

from calendar_agent import CalendarAgent
from email_preprocessor import EmailPreprocessor
from email_tagger import EmailTagger
from spam_detector import UnifiedEmailAnalyzer
from mail_agent.config import config
from mail_agent.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from email_fetcher import EmailFetcher


class MailAgentStateModel(BaseModel):
    email: Dict[str, Any]
    timezone: str
    label_ids: Dict[str, str]
    preprocessed: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    should_act: bool = False
    action_results: Dict[str, Any] = Field(default_factory=dict)
    tagged_email: Optional[Dict[str, Any]] = None
    processed: bool = False
    errors: List[str] = Field(default_factory=list)


class MailAgentState(TypedDict, total=False):
    email: Dict[str, Any]
    timezone: str
    label_ids: Dict[str, str]
    preprocessed: Optional[Dict[str, Any]]
    analysis: Optional[Dict[str, Any]]
    should_act: bool
    action_results: Dict[str, Any]
    tagged_email: Optional[Dict[str, Any]]
    processed: bool
    errors: List[str]


def make_initial_state(email: Dict[str, Any], label_ids: Dict[str, str], timezone: str) -> MailAgentState:
    """Create and validate the initial state for the graph."""
    try:
        validated = MailAgentStateModel(
            email=email,
            timezone=timezone,
            label_ids=label_ids,
        )
        return validated.model_dump()
    except ValidationError as e:
        logger.error(f"Invalid initial state: {e}")
        return {
            "email": email,
            "timezone": timezone,
            "label_ids": label_ids,
            "errors": ["Invalid initial state"],
        }


def _normalize_calendar_event(calendar_event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize LLM calendar event into CalendarAgent.create_event schema."""
    return {
        "summary": calendar_event.get("title"),
        "start": calendar_event.get("start_time"),
        "end": calendar_event.get("end_time"),
        "description": calendar_event.get("description"),
        "attendees": calendar_event.get("attendees"),
    }


def build_graph(
    preprocessor: EmailPreprocessor,
    analyzer: UnifiedEmailAnalyzer,
    calendar_agent: CalendarAgent,
    tagger: EmailTagger,
    fetcher: "EmailFetcher",
):
    """Build and compile the Mail Agent LangGraph pipeline."""

    async def preprocess_node(state: MailAgentState) -> Dict[str, Any]:
        email_data = state.get("email", {})
        logger.info(f"Preprocessing email: {email_data.get('id', 'unknown')}")
        preprocessed = preprocessor.preprocess_email(email_data)
        if preprocessed.get("preprocessing_status") == "error":
            return {
                "preprocessed": preprocessed,
                "errors": (state.get("errors") or [])
                + [preprocessed.get("error_message", "Preprocessing failed")],
            }
        return {"preprocessed": preprocessed}

    async def analyze_node(state: MailAgentState) -> Dict[str, Any]:
        preprocessed = state.get("preprocessed")
        if not preprocessed or preprocessed.get("preprocessing_status") == "error":
            return {}

        email_data = state.get("email", {})
        analysis_input = {
            "from": email_data.get("from"),
            "subject": email_data.get("subject"),
            "body": preprocessed.get("cleaned_body", ""),
            "received_date": email_data.get("date"),
        }

        analysis = await analyzer.analyze_with_retry(
            analysis_input, state.get("timezone", "UTC")
        )
        if not analysis:
            return {
                "errors": (state.get("errors") or [])
                + ["Analysis failed"],
            }

        return {"analysis": analysis}

    async def decide_actions_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if not analysis:
            return {}

        priority = str(analysis.get("priority", "")).upper()
        category = str(analysis.get("category", "")).upper()
        high_priority_levels = {"CRITICAL", "URGENT", "HIGH"}
        important_categories = {"WORK", "PERSONAL", "SCHOOL"}

        should_act = priority in high_priority_levels and category in important_categories
        return {"should_act": should_act}

    async def execute_actions_node(state: MailAgentState) -> Dict[str, Any]:
        if not state.get("should_act"):
            return {}

        analysis = state.get("analysis") or {}
        email_data = state.get("email", {})
        account_id = email_data.get("account_id", "default")

        results: Dict[str, Any] = {}
        for tool in analysis.get("required_tools", []):
            if tool == "calendar":
                calendar_event = analysis.get("calendar_event")
                if calendar_event and calendar_event.get("start_time") and calendar_event.get("title"):
                    event_details = _normalize_calendar_event(calendar_event)
                    results["calendar"] = await calendar_agent.create_event(
                        event_details, account_id
                    )
            elif tool == "reminder":
                reminder = analysis.get("reminder")
                if reminder and reminder.get("due_date"):
                    results["reminder"] = await calendar_agent.create_reminder(
                        title=reminder.get("title"),
                        due_date=reminder.get("due_date"),
                        priority=reminder.get("priority"),
                        description=reminder.get("description"),
                        account_id=account_id,
                    )
            elif tool == "task":
                task = analysis.get("task")
                if task:
                    results["task"] = await calendar_agent.create_task(
                        {
                            "title": task.get("title"),
                            "description": task.get("description"),
                            "due_date": task.get("due_date"),
                            "priority": task.get("priority"),
                            "assignees": task.get("assignees"),
                        },
                        account_id=account_id,
                    )

        return {"action_results": results}

    async def apply_tags_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if not analysis:
            return {}

        email_data = state.get("email", {})
        tagged_email = await tagger.tag_email(email_data, analysis)
        return {"tagged_email": tagged_email}

    async def mark_processed_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        tagged_email = state.get("tagged_email")
        if not analysis or not tagged_email:
            return {}

        if tagged_email.get("tagging_status") != "success":
            return {}

        email_data = state.get("email", {})
        account_id = email_data.get("account_id", "default")
        label_ids = state.get("label_ids", {})

        processed_label = config.get("labels", {}).get("processed", "ProcessedByAgent")
        processed_label_id = label_ids.get(processed_label)
        if not processed_label_id:
            logger.warning("ProcessedByAgent label ID not found")
            return {}

        tag_label_ids = []
        for tag in tagged_email.get("tags", []):
            if tag in label_ids:
                tag_label_ids.append(label_ids[tag])

        try:
            service = fetcher.gmail_services[account_id]
            await asyncio.to_thread(
                service.users().messages().modify(
                    userId="me",
                    id=email_data.get("id"),
                    body={"addLabelIds": [processed_label_id] + tag_label_ids},
                ).execute
            )
            return {"processed": True}
        except Exception as e:
            logger.error(f"Error applying labels to email: {str(e)}")
            return {
                "errors": (state.get("errors") or [])
                + ["Failed to apply labels"],
            }

    builder = StateGraph(MailAgentState)
    builder.add_node("preprocess", preprocess_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("decide_actions", decide_actions_node)
    builder.add_node("execute_actions", execute_actions_node)
    builder.add_node("apply_tags", apply_tags_node)
    builder.add_node("mark_processed", mark_processed_node)

    builder.add_edge(START, "preprocess")
    builder.add_edge("preprocess", "analyze")
    builder.add_edge("analyze", "decide_actions")
    builder.add_edge("decide_actions", "execute_actions")
    builder.add_edge("execute_actions", "apply_tags")
    builder.add_edge("apply_tags", "mark_processed")
    builder.add_edge("mark_processed", END)

    return builder.compile()
