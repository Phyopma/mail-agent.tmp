"""Unified Email Analyzer module.

This module provides a unified interface for analyzing emails using Gemini via
LangChain's ChatGoogleGenerativeAI and structured Pydantic outputs.
"""

import asyncio
import os
import random
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

try:
    from mail_agent.config import config
    from mail_agent.logger import get_logger

    logger = get_logger(__name__)
except Exception:  # pragma: no cover - fallback for standalone usage
    import logging

    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    config = None

# Load environment variables
load_dotenv()

# Token rate limits and tracking (best-effort backoff for Gemini)
TOKEN_LIMIT_PER_MINUTE = 6000
_token_usage = {
    'tokens_used': 0,
    'reset_time': datetime.now(timezone.utc)
}


class EmailCategory(str, Enum):
    WORK = "WORK"
    PERSONAL = "PERSONAL"
    FAMILY = "FAMILY"
    SOCIAL = "SOCIAL"
    MARKETING = "MARKETING"
    SCHOOL = "SCHOOL"
    NEWSLETTER = "NEWSLETTER"
    SHOPPING = "SHOPPING"


class EmailPriority(str, Enum):
    CRITICAL = "CRITICAL"
    URGENT = "URGENT"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    IGNORE = "IGNORE"


class Spam(str, Enum):
    SPAM = "SPAM"
    NOT_SPAM = "NOT_SPAM"


class ToolAction(str, Enum):
    """Enum for tool actions that can be taken on emails."""
    CALENDAR = "calendar"
    REMINDER = "reminder"
    TASK = "task"
    NONE = "none"


class CalendarEvent(BaseModel):
    title: str = Field(description="Title of the calendar event")
    start_time: str = Field(description="Start time of the event in ISO format")
    end_time: Optional[str] = Field(description="End time of the event in ISO format")
    description: Optional[str] = Field(description="Description of the event")
    attendees: Optional[List[str]] = Field(description="List of attendee email addresses")


class Reminder(BaseModel):
    title: str = Field(description="Title of the reminder")
    due_date: str = Field(description="Due date in ISO format")
    priority: str = Field(description="Priority level (high, medium, low)")
    description: Optional[str] = Field(description="Description of the reminder")


class Task(BaseModel):
    title: str = Field(description="Title of the task")
    due_date: Optional[str] = Field(description="Due date in ISO format")
    priority: Optional[str] = Field(description="Priority level (high, medium, low)")
    description: Optional[str] = Field(description="Description of the task")
    assignees: Optional[List[str]] = Field(description="List of assignee email addresses")


class EmailAnalysisResult(BaseModel):
    """Structured output for email analysis following strict schema."""
    is_spam: Spam = Field(
        description="Classifies the email as SPAM or NOT_SPAM based on comprehensive analysis")
    category: EmailCategory = Field(
        description="Determines the primary category of the email")
    priority: EmailPriority = Field(
        description="Assigns priority level based on time sensitivity and impact")
    required_tools: List[str] = Field(
        description="List of required tools for this email")
    calendar_event: Optional[CalendarEvent] = Field(
        default=None, description="Calendar event details if needed")
    reminder: Optional[Reminder] = Field(
        default=None, description="Reminder details if needed")
    task: Optional[Task] = Field(
        default=None, description="Task details if needed")
    reasoning: str = Field(
        description="Reasoning for the tool selection and details")


class UnifiedEmailAnalyzer:
    """Unified interface for analyzing emails using Gemini via LangChain."""

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        max_concurrent_requests: int = 3,
    ) -> None:
        default_model = "gemini-2.5-flash-lite"
        default_temp = 0.1
        default_max_tokens = 2048
        default_timeout = 60

        self.model_name = model or os.environ.get("MAIL_AGENT_GEMINI_MODEL") or (
            config.get("gemini_model") if config else default_model
        )
        self.temperature = temperature if temperature is not None else (
            config.get("gemini_temperature", default_temp) if config else default_temp
        )
        self.max_output_tokens = max_output_tokens if max_output_tokens is not None else (
            config.get("gemini_max_output_tokens", default_max_tokens) if config else default_max_tokens
        )
        self.timeout = timeout if timeout is not None else (
            config.get("gemini_timeout", default_timeout) if config else default_timeout
        )
        self.enable_multimodal_fallback = bool(
            config.get("enable_multimodal_fallback", True) if config else True
        )
        self.multimodal_max_attachments = int(
            config.get("multimodal_max_attachments", 3) if config else 3
        )

        self.logger = logger
        self.logger.info(
            f"Initializing UnifiedEmailAnalyzer with Gemini model: {self.model_name}")

        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        # API Key Management
        self.api_keys = self._load_api_keys()
        self.current_key_index = 0
        
        self.llm = self._build_model()
        self.structured_llm = self._build_structured_model()
        
        # System prompt for email analysis
        self.system_prompt = """
        You are an expert email analyzer specializing in spam detection, categorization, priority assessment, and tool detection.
        Your task is to analyze emails holistically and provide accurate, structured analysis based on comprehensive criteria.
        For spam detection, evaluate these characteristics (multiple indicators suggest higher spam probability):
        1. Sender Patterns:
           - Mismatched or suspicious sender domains
           - Random characters or numbers in sender address
           - Impersonation of legitimate organizations
           - Generic or non-personalized sender names
        2. Content Red Flags:
           - Unsolicited commercial content or marketing materials
           - Poor grammar, spelling errors, or unusual formatting
           - Excessive use of capital letters, punctuation, or urgency words
           - Generic greetings ("Dear Sir/Madam", "Dear User")
           - Too-good-to-be-true offers (prizes, inheritance, investments)
           - Requests for sensitive information or financial transactions
           - Suspicious URLs or cryptocurrency requests
           - Pressure tactics ("Act now!", "Limited time only!")
        For email categorization, use these criteria:
        - WORK:
          * Professional communications (clients, colleagues, business partners)
          * Business-related content (reports, meetings, projects)
          * Work-specific tools or systems mentioned
          * Professional tone and formatting
          * Company domain in sender address
        - PERSONAL:
          * Individual communications outside family context
          * Social activities and events
          * Personal services or subscriptions
          * Informal but not family-intimate tone
          * Personal matters (hobbies, friends, non-family relationships)
        - FAMILY:
          * Communications from family members
          * Family events and gatherings
          * Shared family resources or plans
          * Intimate or family-specific tone
          * Family-related topics (health, household, relatives)
        - SOCIAL:
          * Social media notifications and updates
          * Community group communications
          * Event invitations and RSVPs
          * Social network connections and interactions
          * Platform-specific communications (LinkedIn, Facebook, etc.)
        - MARKETING:
          * Promotional offers and advertisements
          * Product announcements and launches
          * Sales and discount notifications
          * Brand newsletters and updates
          * Marketing campaigns and promotions
        - SCHOOL:
          * Academic institution communications
          * Course-related information
          * Educational resources and materials
          * Student services and administrative updates
          * Academic deadlines and requirements
        - NEWSLETTER:
          * Subscription-based content
          * Regular periodical updates
          * Industry news and insights
          * Curated content collections
          * Publication digests
        - SHOPPING:
          * Order confirmations and tracking
          * Product recommendations
          * Shopping cart reminders
          * Purchase receipts and invoices
          * Shipping notifications
        For priority assessment, use these specific criteria:
        - CRITICAL (immediate response needed):
          * Life-threatening or emergency situations
          * Security breaches or system compromises
          * Immediate legal or regulatory compliance issues
          * Crisis management situations
        - URGENT (24-hour response needed):
          * Explicit deadlines within 24 hours
          * Critical business operations affected
          * Emergency situations or time-sensitive issues
          * Legal or compliance deadlines
        - HIGH (2-3 days response time):
          * Important business matters with approaching deadlines
          * Significant opportunities or issues requiring attention
          * Client or stakeholder escalations
          * Time-sensitive but not immediate emergency
        - NORMAL (within a week):
          * Regular business communications
          * Standard requests or information
          * Updates or status reports
        - LOW (no time pressure):
          * FYI messages or newsletters
          * Non-time-sensitive updates
          * General information sharing
        - IGNORE (no response needed):
          * Pure marketing or promotional content
          * Automated system notifications
          * Subscription confirmations
          * Read-only updates
        For tool detection, be VERY STRICT and conservative about recommending tools. Only suggest tools for emails that CLEARLY require action and contain EXPLICIT information needed for that action. Be extremely cautious about suggesting tools for low-priority or non-work emails.
        IMPORTANT: The system will ONLY execute tool actions for emails that are:
        1. HIGH PRIORITY (CRITICAL, URGENT, or HIGH priority levels only)
        2. From IMPORTANT CATEGORIES (WORK, PERSONAL, or SCHOOL categories only)
        For all other emails (lower priority or other categories), you should generally recommend NONE for required_tools, as the system will not act on these recommendations anyway.
        When determining tools, follow these strict guidelines:
        1. Calendar Events - ONLY recommend when ALL of these conditions are met:
           - SPECIFIC date and time are clearly mentioned (not vague references)
           - Email contains sufficient details to create a meaningful calendar entry
           - Email EXPLICITLY contains a meeting invitation or scheduling request
           - Purpose of the meeting is clearly defined
           - The meeting appears to be important and relevant to the recipient
           If recommended, extract and format all relevant details (title, start/end time, description, attendees)
        2. Tasks - ONLY recommend when ALL of these conditions are met:
           - Email EXPLICITLY assigns work items or action items to the recipient
           - Clear deadlines or timeframes are specified
           - The task has clear ownership and responsibility
           - The task appears to be important and relevant to the recipient's work
           - There is sufficient context to create a meaningful task entry
           If recommended, extract and format all relevant details (title, due date, priority, description, assignees)
        3. Reminders - ONLY recommend when ALL of these conditions are met:
           - Email EXPLICITLY requests follow-up or contains a clear deadline
           - The reminder is for a specific, concrete action (not vague)
           - The reminder has a clear timeframe
           - The reminder appears to be important to the recipient
           - There is sufficient context to create a meaningful reminder
           If recommended, extract and format all relevant details (title, due date, priority, description)
        4. No Tools (NONE) - This should be your DEFAULT recommendation when:
           - Email is purely informational
           - Email is low priority (NORMAL, LOW, or IGNORE)
           - Email is from non-important categories (MARKETING, NEWSLETTER, etc.)
           - Email lacks specific actionable details
           - Email is spam or marketing content
           - There is any uncertainty about whether a tool is truly needed
        Remember: It is better to recommend NO tools than to recommend inappropriate tools. Be extremely conservative in your recommendations.
        For each tool requirement:
        1. First determine if the tool is needed based on the above criteria
        2. If needed, extract all relevant information in the specified format
        3. Provide clear reasoning for why the tool was selected
        4. Ensure all dates and times are in ISO format with respect to the provided timezone
        5. Include all available details in the tool-specific fields
        6. When handling dates and times:
           - Convert all relative time expressions (e.g., 'tomorrow', 'next week') to absolute dates
           - Use the provided timezone for all datetime conversions
           - Format all datetime fields in ISO format with timezone offset
           - Consider daylight saving time when applicable
        Return a response that matches the EmailAnalysisResult schema exactly.
        """

    def _load_api_keys(self) -> List[str]:
        """Load API keys from environment variable, supporting comma-separated list."""
        api_key_str = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key_str:
            self.logger.warning("No GOOGLE_API_KEY found in environment")
            return []
            
        keys = [k.strip() for k in api_key_str.split(",") if k.strip()]
        # Always log how many keys were loaded
        self.logger.info(f"Loaded {len(keys)} API key(s) for rotation (rotation {'enabled' if len(keys) > 1 else 'disabled - need 2+ keys'})")
        return keys

    def rotate_api_key(self) -> bool:
        """Rotate to the next API key. Returns True if rotated, False if no keys or single key."""
        if not self.api_keys or len(self.api_keys) <= 1:
            self.logger.debug(f"Cannot rotate: only {len(self.api_keys) if self.api_keys else 0} key(s) available")
            return False
            
        old_index = self.current_key_index
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self.logger.warning(f"Rotating API key from index {old_index + 1} to {self.current_key_index + 1}/{len(self.api_keys)}")
        
        # Rebuild models with new key
        self.llm = self._build_model()
        self.structured_llm = self._build_structured_model()
        return True

    def _build_structured_model(self):
        """Build structured output runnable with provider-native JSON schema support."""
        return self.llm.with_structured_output(
            EmailAnalysisResult,
            method="json_schema",
            include_raw=True,
        )

    def _build_model(self) -> ChatGoogleGenerativeAI:
        """Build the Gemini chat model with best-effort parameter support."""
        base_kwargs = {
            "model": self.model_name,
            "temperature": self.temperature,
        }
        
        # Explicitly pass the current API key if we have managed keys
        if self.api_keys:
            base_kwargs["google_api_key"] = self.api_keys[self.current_key_index]

        # Try provider-native max_output_tokens with timeout
        try:
            return ChatGoogleGenerativeAI(
                **base_kwargs,
                max_output_tokens=self.max_output_tokens,
                timeout=self.timeout,
            )
        except TypeError:
            pass

        # Retry without timeout
        try:
            return ChatGoogleGenerativeAI(
                **base_kwargs,
                max_output_tokens=self.max_output_tokens,
            )
        except TypeError:
            pass

        # Fallback to max_tokens with timeout
        try:
            return ChatGoogleGenerativeAI(
                **base_kwargs,
                max_tokens=self.max_output_tokens,
                timeout=self.timeout,
            )
        except TypeError:
            return ChatGoogleGenerativeAI(
                **base_kwargs,
                max_tokens=self.max_output_tokens,
            )

    @staticmethod
    def _enum_to_str(value: Any, upper: bool = False) -> str:
        """Normalize enum-like values to plain strings."""
        if value is None:
            return ""
        normalized = str(value)
        if "." in normalized:
            normalized = normalized.split(".")[-1]
        return normalized.upper() if upper else normalized

    def _normalize_analysis_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize structured output into a stable dict contract."""
        normalized = dict(result)
        normalized["is_spam"] = self._enum_to_str(
            normalized.get("is_spam"), upper=True
        )
        normalized["category"] = self._enum_to_str(
            normalized.get("category"), upper=True
        )
        normalized["priority"] = self._enum_to_str(
            normalized.get("priority"), upper=True
        )

        required_tools = normalized.get("required_tools")
        if isinstance(required_tools, list):
            tool_values = [
                self._enum_to_str(tool, upper=False).lower()
                for tool in required_tools
                if self._enum_to_str(tool, upper=False).lower() != "none"
            ]
            # Preserve ordering while removing duplicates.
            normalized["required_tools"] = list(dict.fromkeys(tool_values))
        else:
            normalized["required_tools"] = []

        for detail_field in ("calendar_event", "reminder", "task"):
            detail_value = normalized.get(detail_field)
            if hasattr(detail_value, "model_dump"):
                normalized[detail_field] = detail_value.model_dump()

        reasoning = normalized.get("reasoning")
        normalized["reasoning"] = str(reasoning or "").strip()
        return normalized

    def _is_classification_complete(self, result: Dict[str, Any]) -> bool:
        """Return True only when spam/category/priority are valid enum values."""
        valid_spam = {item.value for item in Spam}
        valid_categories = {item.value for item in EmailCategory}
        valid_priorities = {item.value for item in EmailPriority}

        return (
            result.get("is_spam") in valid_spam
            and result.get("category") in valid_categories
            and result.get("priority") in valid_priorities
        )

    def _finalize_analysis_result(
        self, result: Dict[str, Any], classification_source: str
    ) -> Dict[str, Any]:
        """Finalize result with operational metadata required by the pipeline."""
        normalized = self._normalize_analysis_result(result)
        normalized["classification_source"] = classification_source
        normalized["classification_complete"] = self._is_classification_complete(
            normalized
        )
        if not normalized.get("reasoning"):
            normalized["reasoning"] = "No reasoning provided by model output."
        return normalized

    def _summarize_attachments_for_prompt(self, attachments: List[Dict[str, Any]]) -> str:
        if not attachments:
            return "None"

        lines = []
        for attachment in attachments[: self.multimodal_max_attachments]:
            lines.append(
                f"- filename={attachment.get('filename') or 'unknown'}, "
                f"mime_type={attachment.get('mime_type') or 'unknown'}, "
                f"size={attachment.get('size', 'unknown')}"
            )
        return "\n".join(lines)

    def _build_text_analysis_prompt(self, email_data: Dict[str, Any], timezone: str) -> str:
        attachment_summary = self._summarize_attachments_for_prompt(
            email_data.get("attachments", [])
        )
        return f"""Analyze this email and provide a structured analysis based on the EmailAnalysisResult schema.

From: {email_data.get('from', '')}
Subject: {email_data.get('subject', '')}
Received Date: {email_data.get('received_date', '')}
Body: {email_data.get('body', '')}
Body Quality: {email_data.get('body_quality', 'unknown')}
Attachments:
{attachment_summary}

Note: Use the received date as reference point for any relative time expressions like 'tomorrow', 'next week', etc.
All datetime fields should be in ISO format with {timezone} timezone.
Always return valid values for is_spam, category, and priority.
"""

    def _build_multimodal_content(
        self, email_data: Dict[str, Any], timezone: str
    ) -> List[Dict[str, Any]]:
        """Build multimodal HumanMessage content blocks from hydrated attachments."""
        content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": f"""Analyze this email and attachments. Return valid structured output for EmailAnalysisResult.

From: {email_data.get('from', '')}
Subject: {email_data.get('subject', '')}
Received Date: {email_data.get('received_date', '')}
Body (possibly short or empty): {email_data.get('body', '')}
Body Quality: {email_data.get('body_quality', 'unknown')}

Use attachment content as primary context when body text is weak.
All datetime fields should be in ISO format with {timezone} timezone.
Always return valid values for is_spam, category, and priority.
""",
            }
        ]

        attachment_count = 0
        for attachment in email_data.get("attachments", []):
            if attachment_count >= self.multimodal_max_attachments:
                break
            data_b64 = attachment.get("data_b64")
            mime_type = str(attachment.get("mime_type") or "")
            if not data_b64:
                continue
            if mime_type.startswith("image/"):
                content.append(
                    {"type": "image", "base64": data_b64, "mime_type": mime_type}
                )
                attachment_count += 1
            elif mime_type == "application/pdf":
                content.append(
                    {"type": "file", "base64": data_b64, "mime_type": mime_type}
                )
                attachment_count += 1
        return content

    async def _invoke_structured_analysis(
        self, messages: List[Any]
    ) -> Optional[Dict[str, Any]]:
        """Invoke structured LLM and safely extract parsed output."""
        async with self.semaphore:
            if hasattr(self.structured_llm, "ainvoke"):
                response = await self.structured_llm.ainvoke(messages)
            else:
                response = await asyncio.to_thread(self.structured_llm.invoke, messages)

        parsed: Any = response
        if isinstance(response, dict) and "parsed" in response:
            parsed = response.get("parsed")

        if parsed is None:
            return None
        if hasattr(parsed, "model_dump"):
            parsed = parsed.model_dump()
        if not isinstance(parsed, dict):
            return None
        return self._normalize_analysis_result(parsed)

    def _should_use_multimodal_fallback(self, email_data: Dict[str, Any]) -> bool:
        """Decide when to run multimodal fallback analysis."""
        if not self.enable_multimodal_fallback:
            return False
        if not email_data.get("attachments"):
            return False

        body_quality = str(email_data.get("body_quality") or "").lower()
        if body_quality in {"short_text", "no_text"}:
            return True

        body = str(email_data.get("body") or "").strip()
        return len(body) < 80 and bool(email_data.get("has_non_text_content"))

    def _apply_heuristic_fallback(
        self, email_data: Dict[str, Any], reason: str
    ) -> Dict[str, Any]:
        """Deterministic fallback that always returns complete classification."""
        sender = str(email_data.get("from", "")).lower()
        subject = str(email_data.get("subject", "")).lower()
        body = str(email_data.get("body", "")).lower()
        text = f"{sender}\n{subject}\n{body}"

        spam_markers = [
            "winner",
            "lottery",
            "inheritance",
            "bank details",
            "act now",
            "limited time",
            "urgent business proposal",
            "crypto investment",
        ]
        emergency_markers = ["security breach", "urgent", "asap", "immediately", "deadline"]
        marketing_markers = ["unsubscribe", "sale", "discount", "promotion", "offer"]
        newsletter_markers = ["newsletter", "digest", "weekly update", "daily briefing"]
        shopping_markers = ["order", "receipt", "invoice", "shipment", "tracking"]
        school_markers = [".edu", "course", "class", "assignment", "exam"]
        family_markers = ["mom", "dad", "family", "brother", "sister"]
        social_markers = ["linkedin", "facebook", "instagram", "twitter", "social"]
        work_markers = ["meeting", "project", "client", "stakeholder", "deadline", "team"]

        spam_score = sum(1 for marker in spam_markers if marker in text)
        is_spam = Spam.SPAM.value if spam_score >= 2 else Spam.NOT_SPAM.value

        if is_spam == Spam.SPAM.value:
            category = EmailCategory.MARKETING.value
            priority = EmailPriority.IGNORE.value
        elif any(marker in text for marker in school_markers):
            category = EmailCategory.SCHOOL.value
            priority = EmailPriority.HIGH.value if "deadline" in text else EmailPriority.NORMAL.value
        elif any(marker in text for marker in shopping_markers):
            category = EmailCategory.SHOPPING.value
            priority = EmailPriority.LOW.value
        elif any(marker in text for marker in newsletter_markers):
            category = EmailCategory.NEWSLETTER.value
            priority = EmailPriority.IGNORE.value
        elif any(marker in text for marker in marketing_markers):
            category = EmailCategory.MARKETING.value
            priority = EmailPriority.IGNORE.value
        elif any(marker in text for marker in family_markers):
            category = EmailCategory.FAMILY.value
            priority = EmailPriority.NORMAL.value
        elif any(marker in text for marker in social_markers):
            category = EmailCategory.SOCIAL.value
            priority = EmailPriority.LOW.value
        elif any(marker in text for marker in work_markers):
            category = EmailCategory.WORK.value
            priority = (
                EmailPriority.URGENT.value
                if any(marker in text for marker in emergency_markers)
                else EmailPriority.NORMAL.value
            )
        else:
            category = EmailCategory.PERSONAL.value
            priority = (
                EmailPriority.URGENT.value
                if any(marker in text for marker in emergency_markers)
                else EmailPriority.NORMAL.value
            )

        fallback = {
            "is_spam": is_spam,
            "category": category,
            "priority": priority,
            "required_tools": [],
            "calendar_event": None,
            "reminder": None,
            "task": None,
            "reasoning": f"Heuristic fallback applied: {reason}",
        }
        return self._finalize_analysis_result(fallback, "heuristic")

    async def analyze_email(self, email_data: Dict[str, Any], timezone: str = "UTC") -> Optional[Dict[str, Any]]:
        """Analyze an email with text-first + multimodal + deterministic fallback."""
        await self.wait_for_rate_limit()

        self.logger.info(
            f"Analyzing email from {email_data.get('from', 'Unknown')} with subject: {email_data.get('subject', 'No subject')}"
        )

        # Stage A: Text-only structured analysis.
        text_prompt = self._build_text_analysis_prompt(email_data, timezone)
        text_messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=text_prompt),
        ]
        stage_a = await self._invoke_structured_analysis(text_messages)
        if stage_a:
            finalized_a = self._finalize_analysis_result(stage_a, "llm_text")
            if finalized_a.get("classification_complete"):
                return finalized_a

        # Stage B: Multimodal structured analysis for weak body content.
        if self._should_use_multimodal_fallback(email_data):
            multimodal_content = self._build_multimodal_content(email_data, timezone)
            # Only run multimodal if we actually have binary blocks besides text.
            if len(multimodal_content) > 1:
                multimodal_messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=multimodal_content),
                ]
                stage_b = await self._invoke_structured_analysis(multimodal_messages)
                if stage_b:
                    finalized_b = self._finalize_analysis_result(stage_b, "llm_multimodal")
                    if finalized_b.get("classification_complete"):
                        return finalized_b

        # Stage C: Deterministic fallback to guarantee category/priority.
        return self._apply_heuristic_fallback(
            email_data, reason="LLM output was incomplete after retries/fallback"
        )

    async def wait_for_rate_limit(self, tokens_used: Optional[int] = None) -> None:
        """Wait if we're approaching rate limits (RPM or TPM)."""
        global _token_usage
        
        # RPM Limiting (Requests Per Minute)
        if not hasattr(self, '_request_timestamps'):
            self._request_timestamps = []
            
        now = datetime.now(timezone.utc)
        # Remove timestamps older than 60 seconds
        self._request_timestamps = [t for t in self._request_timestamps if (now - t).total_seconds() < 60]
        
        # If we have >= 12 requests in the last minute (conservative limit for 15 RPM)
        if len(self._request_timestamps) >= 12:
            # Try to rotate key first
            if self.rotate_api_key():
                self.logger.info("Approaching RPM limit (12/15). Rotated API key to avoid wait.")
                # Reset local request counter for the new key (simplistic assumption: new key has fresh quota)
                self._request_timestamps = []
            else:
                # If cannot rotate, then wait
                oldest_request = self._request_timestamps[0]
                wait_time = 60 - (now - oldest_request).total_seconds() + 1 # +1 buffer
                wait_time = max(1, wait_time)
                self.logger.info(f"Approaching RPM limit ({len(self._request_timestamps)}/15). Waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
        # Record this request
        self._request_timestamps.append(datetime.now(timezone.utc))

        # TPM Limiting (Tokens Per Minute) - Existing Logic
        if (now - _token_usage['reset_time']).total_seconds() >= 60:
            _token_usage = {'tokens_used': 0, 'reset_time': now}
        
        if tokens_used:
            _token_usage['tokens_used'] += tokens_used

        if _token_usage['tokens_used'] > TOKEN_LIMIT_PER_MINUTE * 0.8:
            # Try to rotate key first for token limit too
            if self.rotate_api_key():
                 self.logger.info(f"Approaching token limit ({_token_usage['tokens_used']}/{TOKEN_LIMIT_PER_MINUTE}). Rotated API key to avoid wait.")
                 _token_usage = {'tokens_used': 0, 'reset_time': datetime.now(timezone.utc)}
            else:
                seconds_until_reset = 60 - (now - _token_usage['reset_time']).total_seconds()
                wait_time = max(1, seconds_until_reset)
                self.logger.info(
                    f"Approaching token limit ({_token_usage['tokens_used']}/{TOKEN_LIMIT_PER_MINUTE}). Waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                _token_usage = {
                    'tokens_used': 0,
                    'reset_time': datetime.now(timezone.utc)
                }

    async def analyze_with_retry(self, input_data: Dict[str, Any], timezone: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Analyze an email with retry logic for transient errors."""
        retries = 0
        base_wait = 2

        while retries <= max_retries:
            try:
                result = await self.analyze_email(input_data, timezone)
                return result
            except Exception as e:
                error_msg = str(e).lower()
                retries += 1
                
                # Check for Quota/Rate Limit Exceeded
                if any(term in error_msg for term in ['rate limit', 'too many requests', 'quota', 'capacity', 'resource_exhausted', '429']):
                    # Try to rotate key first
                    if self.rotate_api_key():
                        self.logger.info(f"Rate limit hit. Switched API key and retrying immediately.")
                        continue # Retry immediately with new key
                        
                    # The API usually asks for ~10s wait. We'll wait 20s to be safe and let the bucket refill.
                    wait_time = 20 + (random.random() * 5)
                    self.logger.warning(
                        f"Rate limit hit ({type(e).__name__}). Retry {retries}/{max_retries} after {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                
                elif retries < max_retries:
                    wait_time = base_wait * (2 ** (retries - 1))
                    self.logger.error(
                        f"Error analyzing email (retry {retries}/{max_retries} after {wait_time:.2f}s): {str(e)}")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Failed to analyze email after {max_retries} retries: {str(e)}")
                    return self._apply_heuristic_fallback(
                        input_data,
                        reason=f"LLM unavailable after {max_retries} retries: {type(e).__name__}",
                    )

        return self._apply_heuristic_fallback(
            input_data, reason="Retry loop exhausted unexpectedly"
        )

    async def analyze_batch_with_rate_limiting(self, email_batch: List[Dict[str, Any]], timezone: str, chunk_size: int = 3) -> List[Optional[Dict[str, Any]]]:
        """Analyze a batch of emails with simple chunking."""
        results: List[Optional[Dict[str, Any]]] = []
        for i in range(0, len(email_batch), chunk_size):
            chunk = email_batch[i:i + chunk_size]
            chunk_results = []
            for input_data in chunk:
                chunk_results.append(await self.analyze_with_retry(input_data, timezone))
                if input_data != chunk[-1]:
                    await asyncio.sleep(0.5)
            results.extend(chunk_results)
        return results
