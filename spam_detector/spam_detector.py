"""Spam Detection Module for Mail Agent.

This module uses a local LLM (Llama) through Ollama to detect spam emails.
It provides structured output and integrates with the email preprocessing pipeline.
"""

from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import json
import asyncio
from enum import Enum
from typing import List as PyList


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


# class EmailAction(BaseModel):
#     description: str
#     deadline: Optional[str] = None

# class EmailTool(str, Enum):
#     CALENDAR = "calendar"
#     DOCUMENT_VIEWER = "document_viewer"
#     TASK_MANAGER = "task_manager"
#     COMMUNICATION_TOOL = "communication_tool"
#     FILE_SHARING = "file_sharing"

class CalendarEvent(BaseModel):
    title: str = Field(description="Title of the calendar event")
    start_time: str = Field(
        description="Start time of the event in ISO format")
    end_time: Optional[str] = Field(
        description="End time of the event in ISO format")
    description: Optional[str] = Field(description="Description of the event")
    attendees: Optional[List[str]] = Field(
        description="List of attendee email addresses")


class Reminder(BaseModel):
    title: str = Field(description="Title of the reminder")
    due_date: str = Field(description="Due date in ISO format")
    priority: str = Field(description="Priority level (high, medium, low)")
    description: Optional[str] = Field(
        description="Description of the reminder")


class ToolAction(str, Enum):
    CALENDAR = "calendar"
    REMINDER = "reminder"
    TASK = "task"
    NONE = "none"


class Task(BaseModel):
    title: str = Field(description="Title of the task")
    due_date: Optional[str] = Field(description="Due date in ISO format")
    priority: Optional[str] = Field(
        description="Priority level (high, medium, low)")
    description: Optional[str] = Field(description="Description of the task")
    assignees: Optional[List[str]] = Field(
        description="List of assignee email addresses")


class EmailAnalysisResult(BaseModel):
    """Structured output for email analysis following OpenAI guidelines."""
    is_spam: Spam = Field(
        description="Classifies the email as SPAM or NOT_SPAM based on comprehensive analysis of sender patterns, content characteristics, and red flags. Consider factors like suspicious domains, urgency tactics, unsolicited offers, and requests for sensitive information.")

    category: EmailCategory = Field(
        description="Determines the primary category (WORK/PERSONAL/FAMILY/SOCIAL/MARKETING/SCHOOL/NEWSLETTER/SHOPPING) based on sender relationship, content context, communication style, and purpose. Analyzes tone, formatting, domain, and specific content indicators unique to each category.")
    priority: EmailPriority = Field(
        description="Assigns priority level (CRITICAL/URGENT/HIGH/NORMAL/LOW/IGNORE) based on time sensitivity, impact, and required action. Considers explicit deadlines, business impact, emergency nature, and whether a response is needed.")
    required_tools: List[ToolAction] = Field(
        description="List of required tools for this email")
    calendar_event: Optional[CalendarEvent] = Field(
        description="Calendar event details if needed")
    reminder: Optional[Reminder] = Field(
        description="Reminder details if needed")
    task: Optional[Task] = Field(
        description="Task details if needed")
    reasoning: str = Field(
        description="Reasoning for the tool selection and details")


class UnifiedEmailAnalyzer:
    """Unified email analyzer supporting multiple LLM backends."""

    def __init__(self, backend: str = "ollama",
                 max_concurrent_requests: int = 3):
        """Initialize the email analyzer.

        Args:
            backend: LLM backend to use ("ollama" or "lmstudio")
            model_name: Name of the model to use
            base_url: Base URL for LMStudio API
            max_concurrent_requests: Maximum number of concurrent requests
        """
        if backend == "ollama":
            self.llm = ChatOpenAI(
                base_url="http://localhost:11434/v1",
                api_key="not-needed",
                model_name="llama3.1:8b-instruct-q4_K_M",
                # model_name="qwen2.5:14b-instruct-q4_0",
                # model_name="granite3.1-dense:8b-instruct-q4_K_S",
                temperature=0,
                max_tokens=8000,
                callbacks=None  # Disable LangSmith tracking
            )
        else:  # lmstudio
            self.llm = ChatOpenAI(
                base_url="http://localhost:1234/v1",  # Default LMStudio port
                api_key="not-needed",
                # model_name="lmstudio-community/Qwen2.5-14B-Instruct-1M-GGUF",
                # model_name="qwen2.5-14b-instruct-1m",
                model_name="meta-llama-3.1-8b-instruct",
                temperature=0,
                max_tokens=8000,
                callbacks=None  # Disable LangSmith tracking
            )

        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        # Optimized system prompt following OpenAI guidelines
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
          * Mission-critical system failures

        - URGENT (24-hour response needed):
          * Explicit deadlines within 24 hours
          * Critical business operations affected
          * Emergency situations or time-sensitive issues
          * Legal or compliance deadlines
          * Immediate action required to prevent negative consequences

        - HIGH (2-3 days response time):
          * Important business matters with approaching deadlines
          * Significant opportunities or issues requiring attention
          * Client or stakeholder escalations
          * Time-sensitive but not immediate emergency

        - NORMAL (within a week):
          * Regular business communications
          * Standard requests or information
          * Updates or status reports
          * General correspondence requiring action

        - LOW (no time pressure):
          * FYI messages or newsletters
          * Non-time-sensitive updates
          * General information sharing
          * No specific action required

        - IGNORE (no response needed):
          * Pure marketing or promotional content
          * Automated system notifications
          * Subscription confirmations
          * Read-only updates
          * No action or response expected

        For tool detection, be VERY STRICT and conservative about recommending tools. Only suggest tools for emails that CLEARLY require action and contain EXPLICIT information needed for that action. Be extremely cautious about suggesting tools for low-priority or non-work emails.
        
        IMPORTANT: The system will ONLY execute tool actions for emails that are:
        1. HIGH PRIORITY (CRITICAL, URGENT, or HIGH priority levels only)
        2. From IMPORTANT CATEGORIES (WORK, PERSONAL, or SCHOOL categories only)
        
        For all other emails (lower priority or other categories), you should generally recommend NONE for required_tools, as the system will not act on these recommendations anyway.
        
        When determining tools, follow these strict guidelines:

        1. Calendar Events - ONLY recommend when ALL of these conditions are met:
           - Email EXPLICITLY contains a meeting invitation or scheduling request
           - SPECIFIC date and time are clearly mentioned (not vague references)
           - Purpose of the meeting is clearly defined
           - Email contains sufficient details to create a meaningful calendar entry
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

        Provide your analysis in a structured format with:
        1. Spam classification (SPAM/NOT_SPAM) - based on comprehensive spam indicators
        2. Email category (WORK/PERSONAL/FAMILY/SOCIAL/MARKETING/SCHOOL/NEWSLETTER/SHOPPING) - based on content and context analysis
        3. Priority level (CRITICAL/URGENT/HIGH/NORMAL/LOW/IGNORE) - based on time sensitivity and impact
        4. Required tools (List of calendar, reminder, tasks or none) - based on content analysis
        5. Detailed tool information if needed (calendar_event or reminder fields)
        6. Clear reasoning for all decisions
        """

    async def analyze_email(self, email_data: Dict[str, Any], timezone: str = "America/Los_Angeles") -> Optional[Dict[str, Any]]:
        """Analyze email using the configured LLM backend.

        Args:
            email_data: Dictionary containing email information

        Returns:
            Dictionary containing analysis results
        """
        try:
            # Use structured output with the EmailAnalysisResult model
            structured_llm = self.llm.with_structured_output(
                EmailAnalysisResult)

            # Prepare the analysis prompt
            analysis_prompt = f"""Analyze this email and provide a structured analysis:
From: {email_data.get('from', '')}
Subject: {email_data.get('subject', '')}
Received Date: {email_data.get('received_date', '')}
Body: {email_data.get('body', '')}

Note: Use the received date as reference point for any relative time expressions like 'tomorrow', 'next week', etc.
All datetime fields should be in ISO format with {timezone}timezone."""

            messages = [
                (
                    "system",
                    self.system_prompt,
                ),
                ("human", analysis_prompt),
            ]  # Get structured response from LLM
            result = await structured_llm.ainvoke(messages)

            return {
                'is_spam': result.is_spam,
                'category': result.category,
                'priority': result.priority,
                'required_tools': result.required_tools,
                'calendar_event': result.calendar_event,
                'reminder': result.reminder,
                'reasoning': result.reasoning
            }

        except Exception as e:
            print(f"Error during email analysis: {str(e)}")
            return None

    async def analyze_email_batch(self, email_data_list: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
        """Analyze multiple emails concurrently.

        Args:
            email_data_list: List of dictionaries containing email information

        Returns:
            List of dictionaries containing analysis results
        """
        async def process_single_email(email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with self.semaphore:
                return await self.analyze_email(email_data)

        tasks = [process_single_email(email_data)
                 for email_data in email_data_list]
        return await asyncio.gather(*tasks)
