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
    classification_complete: bool = False
    classification_source: Optional[str] = None
    spam_disposition_status: Optional[str] = None
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
    classification_complete: bool
    classification_source: Optional[str]
    spam_disposition_status: Optional[str]
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

    enforce_both_labels = bool(config.get("enforce_both_labels", True))
    spam_disposition = str(config.get("spam_disposition", "trash")).lower()
    multimodal_max_attachment_bytes = int(
        config.get("multimodal_max_attachment_bytes", 2000000)
    )
    metrics = {
        "classification_incomplete_count": 0,
        "fallback_used_count": 0,
        "spam_trashed_count": 0,
        "processed_without_both_labels": 0,
    }

    def _increment_metric(name: str) -> None:
        metrics[name] += 1
        logger.info(f"metric={name} value={metrics[name]}")

    def _is_spam(analysis: Optional[Dict[str, Any]]) -> bool:
        if not analysis:
            return False
        return str(analysis.get("is_spam", "")).upper() == "SPAM"

    def _expected_tags(analysis: Dict[str, Any]) -> List[str]:
        priority = str(analysis.get("priority", "")).title()
        category = str(analysis.get("category", "")).title()
        tags: List[str] = []
        if priority:
            tags.append(f"Priority/{priority}")
        if category:
            tags.append(f"Category/{category}")
        return tags

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
        account_id = email_data.get("account_id", "default")
        hydrated_attachments = email_data.get("attachments", [])
        if hydrated_attachments:
            hydrated_attachments = await fetcher.hydrate_attachment_content(
                account_id=account_id,
                message_id=email_data.get("id", ""),
                attachments=hydrated_attachments,
                max_bytes=multimodal_max_attachment_bytes,
            )

        analysis_input = {
            "from": email_data.get("from"),
            "subject": email_data.get("subject"),
            "body": preprocessed.get("cleaned_body", ""),
            "received_date": email_data.get("date"),
            "body_quality": preprocessed.get("body_quality", "unknown"),
            "text_length": preprocessed.get("text_length", 0),
            "attachments": hydrated_attachments,
            "has_non_text_content": bool(email_data.get("has_non_text_content")),
        }

        analysis = await analyzer.analyze_with_retry(
            analysis_input, state.get("timezone", "UTC")
        )
        if not analysis:
            return {
                "errors": (state.get("errors") or [])
                + ["Analysis failed"],
            }

        classification_source = str(
            analysis.get("classification_source", "llm_text")
        ).lower()
        if classification_source == "heuristic":
            _increment_metric("fallback_used_count")

        return {
            "analysis": analysis,
            "classification_source": classification_source,
            "classification_complete": bool(
                analysis.get("classification_complete", False)
            ),
        }

    async def validate_classification_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if not analysis:
            return {"classification_complete": False}

        # Spam handling does not require category/priority completeness.
        if _is_spam(analysis):
            return {
                "classification_complete": bool(
                    analysis.get("classification_complete", False)
                )
            }

        is_complete = bool(analysis.get("classification_complete", False))
        if not is_complete:
            _increment_metric("classification_incomplete_count")
            errors = state.get("errors") or []
            if enforce_both_labels:
                errors = errors + ["Classification incomplete: missing category or priority"]
            return {
                "classification_complete": False,
                "errors": errors,
            }

        return {"classification_complete": True}

    async def spam_disposition_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if not _is_spam(analysis):
            return {"spam_disposition_status": "not_spam"}

        if spam_disposition != "trash":
            logger.info(
                "Spam detected but spam_disposition is not 'trash'; leaving message untouched."
            )
            return {"spam_disposition_status": "skipped_by_config"}

        email_data = state.get("email", {})
        account_id = email_data.get("account_id", "default")
        service = fetcher.gmail_services.get(account_id)
        if not service:
            return {
                "spam_disposition_status": "error",
                "errors": (state.get("errors") or []) + ["Gmail service not found for spam trash"],
            }

        try:
            await asyncio.to_thread(
                service.users()
                .messages()
                .trash(userId="me", id=email_data.get("id"))
                .execute
            )
            _increment_metric("spam_trashed_count")
            return {
                "spam_disposition_status": "trashed",
                "processed": True,
            }
        except Exception as e:
            logger.error(f"Error trashing spam email: {str(e)}")
            return {
                "spam_disposition_status": "error",
                "errors": (state.get("errors") or []) + ["Failed to trash spam email"],
            }

    async def decide_actions_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        if not analysis:
            return {}
        if _is_spam(analysis):
            return {"should_act": False}
        if enforce_both_labels and not state.get("classification_complete", False):
            return {"should_act": False}

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
        if _is_spam(analysis):
            return {}
        if enforce_both_labels and not state.get("classification_complete", False):
            return {}

        email_data = state.get("email", {})
        tagged_email = await tagger.tag_email(email_data, analysis)
        return {"tagged_email": tagged_email}

    async def mark_processed_node(state: MailAgentState) -> Dict[str, Any]:
        analysis = state.get("analysis")
        tagged_email = state.get("tagged_email")
        if not analysis or not tagged_email:
            return {}
        if _is_spam(analysis):
            return {}
        if enforce_both_labels and not state.get("classification_complete", False):
            _increment_metric("processed_without_both_labels")
            return {
                "errors": (state.get("errors") or []) + ["Skipped processing due to incomplete classification"],
            }

        if tagged_email.get("tagging_status") != "success":
            if enforce_both_labels:
                _increment_metric("processed_without_both_labels")
            return {}

        email_data = state.get("email", {})
        account_id = email_data.get("account_id", "default")
        label_ids = state.get("label_ids", {})

        processed_label = config.get("labels", {}).get("processed", "ProcessedByAgent")
        processed_label_id = label_ids.get(processed_label)
        if not processed_label_id:
            logger.warning("ProcessedByAgent label ID not found")
            return {}

        required_tags = _expected_tags(analysis)
        tag_label_ids: List[str] = []

        if enforce_both_labels:
            missing_applied_tags = [
                tag for tag in required_tags if tag not in tagged_email.get("tags", [])
            ]
            if missing_applied_tags:
                _increment_metric("processed_without_both_labels")
                return {
                    "errors": (state.get("errors") or [])
                    + [f"Required tags missing from tagged email: {missing_applied_tags}"],
                }

            missing_label_ids = [tag for tag in required_tags if tag not in label_ids]
            if missing_label_ids:
                _increment_metric("processed_without_both_labels")
                logger.warning(f"Missing Gmail label IDs for required tags: {missing_label_ids}")
                return {
                    "errors": (state.get("errors") or [])
                    + [f"Missing label IDs for required tags: {missing_label_ids}"],
                }

            tag_label_ids = [label_ids[tag] for tag in required_tags]
        else:
            for tag in tagged_email.get("tags", []):
                if tag in label_ids:
                    tag_label_ids.append(label_ids[tag])

        try:
            service = fetcher.gmail_services[account_id]
            add_label_ids = [processed_label_id] + tag_label_ids
            await asyncio.to_thread(
                service.users().messages().modify(
                    userId="me",
                    id=email_data.get("id"),
                    body={"addLabelIds": add_label_ids},
                ).execute
            )
            return {"processed": True}
        except Exception as e:
            logger.error(f"Error applying labels to email: {str(e)}")
            return {
                "errors": (state.get("errors") or [])
                + ["Failed to apply labels"],
            }

    def route_after_validation(state: MailAgentState) -> str:
        if not state.get("analysis"):
            return END
        if _is_spam(state.get("analysis")):
            return "spam_disposition"
        if enforce_both_labels and not state.get("classification_complete", False):
            return END
        return "decide_actions"

    builder = StateGraph(MailAgentState)
    builder.add_node("preprocess", preprocess_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("validate_classification", validate_classification_node)
    builder.add_node("spam_disposition", spam_disposition_node)
    builder.add_node("decide_actions", decide_actions_node)
    builder.add_node("execute_actions", execute_actions_node)
    builder.add_node("apply_tags", apply_tags_node)
    builder.add_node("mark_processed", mark_processed_node)

    builder.add_edge(START, "preprocess")
    builder.add_edge("preprocess", "analyze")
    builder.add_edge("analyze", "validate_classification")
    builder.add_conditional_edges(
        "validate_classification",
        route_after_validation,
        {
            "spam_disposition": "spam_disposition",
            "decide_actions": "decide_actions",
            END: END,
        },
    )
    builder.add_edge("spam_disposition", END)
    builder.add_edge("decide_actions", "execute_actions")
    builder.add_edge("execute_actions", "apply_tags")
    builder.add_edge("apply_tags", "mark_processed")
    builder.add_edge("mark_processed", END)

    return builder.compile()
