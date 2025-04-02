"""Unified Email Analyzer module.

This module provides a unified interface for analyzing emails using different LLM backends.
"""

import os
import json
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional, Union
from enum import Enum, auto
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()


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
    """Unified interface for analyzing emails using different backends."""

    def __init__(self, analyzer_type=None, backend="groq", max_concurrent_requests: int = 3):
        """Initialize the analyzer with the specified backend type.

        Args:
            analyzer_type: Legacy parameter name for backend type
            backend: Type of backend to use
            max_concurrent_requests: Maximum number of concurrent requests
        """
        # For backward compatibility, accept both analyzer_type and backend
        self.backend_type = backend or analyzer_type or os.environ.get(
            "MAIL_AGENT_ANALYZER", "groq")

        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Initializing UnifiedEmailAnalyzer with backend: {self.backend_type}")
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

        # Initialize the appropriate backend
        if self.backend_type == "openrouter":
            self._initialize_openrouter()
        elif self.backend_type == "ollama":
            self._initialize_ollama()
        elif self.backend_type == "lmstudio":
            self._initialize_lmstudio()
        elif self.backend_type == "groq":
            self._initialize_groq()
        else:
            self.logger.warning(
                f"Unknown backend type: {self.backend_type}. Falling back to OpenRouter.")
            self._initialize_openrouter()

        # Setup the system prompt
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
        Your response must be a single valid serializable JSON object that strictly follows this structure (no additional fields or explanations outside the JSON):
        { "is_spam": "SPAM or NOT_SPAM",
          "category": "WORK or PERSONAL or FAMILY or SOCIAL or MARKETING or SCHOOL or NEWSLETTER or SHOPPING",
          "priority": "CRITICAL or URGENT or HIGH or NORMAL or LOW or IGNORE",
          "required_tools": ["calendar", "reminder", "task", "none"],
          "calendar_event": null or {
            "title": "string",
            "start_time": "ISO datetime string",
            "end_time": "ISO datetime string or null",
            "description": "string or null",
            "attendees": ["email addresses"] or null
          },
          "reminder": null or {
            "title": "string",
            "due_date": "ISO datetime string",
            "priority": "high/medium/low",
            "description": "string or null"
          },
          "task": null or {
            "title": "string",
            "due_date": "ISO datetime string or null",
            "priority": "high/medium/low or null",
            "description": "string or null",
            "assignees": ["email addresses"] or null
          },
          "reasoning": "string explaining your analysis and tool recommendations"
        }
        Make sure the values for is_spam, category, priority, and required_tools strictly match the expected enum values.
        Do not add any explanations or text outside of this serializable JSON structure.
        """

    def _initialize_openrouter(self):
        """Initialize OpenRouter backend."""
        self.logger.info("Initializing OpenRouter backend")
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        if not self.openrouter_api_key:
            self.logger.error(
                "OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable.")
        else:
            self.logger.info("OpenRouter API key found")
            try:
                import openai
                self.client = openai.OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.openrouter_api_key,
                )
                self.model_name = "deepseek/deepseek-r1-distill-llama-70b:free"
            except ImportError:
                self.logger.error(
                    "OpenAI package not installed. Please install with 'pip install openai'.")
            except Exception as e:
                self.logger.error(
                    f"Error initializing OpenRouter client: {str(e)}")

    def _initialize_ollama(self):
        """Initialize Ollama backend."""
        self.logger.info("Initializing Ollama backend")

        try:
            import openai
            self.client = openai.OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="not-needed",
            )
            self.model_name = "llama3:latest"
        except ImportError:
            self.logger.error(
                "OpenAI package not installed. Please install with 'pip install openai'.")
        except Exception as e:
            self.logger.error(
                f"Error initializing Ollama client: {str(e)}")

    def _initialize_lmstudio(self):
        """Initialize LM Studio backend."""
        self.logger.info("Initializing LM Studio backend")
        self.lmstudio_url = os.environ.get(
            "LMSTUDIO_URL", "http://localhost:1234/v1")
        self.logger.info(f"Using LM Studio URL: {self.lmstudio_url}")
        try:
            import openai
            self.client = openai.OpenAI(
                base_url=self.lmstudio_url,
                api_key="not-needed",
            )
            self.model_name = "meta-llama-3.1-8b-instruct"
        except ImportError:
            self.logger.error(
                "OpenAI package not installed. Please install with 'pip install openai'.")
        except Exception as e:
            self.logger.error(f"Error initializing LM Studio client: {str(e)}")

    def _initialize_groq(self):
        """Initialize Groq backend."""
        self.logger.info("Initializing Groq backend")
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        if not self.groq_api_key:
            self.logger.error(
                "Groq API key not found. Please set GROQ_API_KEY environment variable.")
        else:
            try:
                import openai
                self.client = openai.OpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=self.groq_api_key,
                )
                self.model_name = "deepseek-r1-distill-llama-70b"
            except ImportError:
                self.logger.error(
                    "OpenAI package not installed. Please install with 'pip install openai'.")
            except Exception as e:
                self.logger.error(f"Error initializing Groq client: {str(e)}")

    def _clean_json_response(self, response_text: str) -> str:
        """Clean the response text to extract valid JSON.

        Args:
            response_text: Raw response text from the model

        Returns:
            Cleaned JSON string
        """
        # Handle case where JSON is wrapped in markdown code blocks with or without language specifier
        if "```" in response_text:
            # Extract content between triple backticks
            pattern = r"```(?:json)?(.*?)```"
            matches = re.findall(pattern, response_text, re.DOTALL)
            if matches:
                # Take the first JSON block found
                return matches[0].strip()

        # If no code blocks or extraction failed, try to find JSON object directly
        # Look for content that starts with { and ends with }
        pattern = r"\{.*\}"
        matches = re.findall(pattern, response_text, re.DOTALL)
        if matches:
            return matches[0].strip()

        # If all parsing attempts fail, return the original text
        return response_text

    async def analyze_email(self, email_data: Dict[str, Any], timezone: str = "UTC") -> Optional[Dict[str, Any]]:
        """Analyze an email using the configured LLM backend.

        Args:
            email_data: Email data dictionary with 'from', 'subject', 'body'
            timezone: Timezone to use for datetime parsing

        Returns:
            Dictionary with analysis results or None if analysis failed
        """
        self.logger.info(
            f"Analyzing email from {email_data.get('from', 'Unknown')} with subject: {email_data.get('subject', 'No subject')}")

        # Prepare the analysis prompt
        analysis_prompt = f"""Analyze this email and provide a structured analysis as a valid JSON object that strictly follows the EmailAnalysisResult schema:

From: {email_data.get('from', '')}
Subject: {email_data.get('subject', '')}
Received Date: {email_data.get('received_date', '')}
Body: {email_data.get('body', '')}

Note: Use the received date as reference point for any relative time expressions like 'tomorrow', 'next week', etc.
All datetime fields should be in ISO format with {timezone} timezone.

Your response must be a valid serializable JSON object with ONLY these fields (no explanations outside the JSON):
- is_spam: Must be exactly "SPAM" or "NOT_SPAM"
- category: Must be exactly one of: "WORK", "PERSONAL", "FAMILY", "SOCIAL", "MARKETING", "SCHOOL", "NEWSLETTER", "SHOPPING"
- priority: Must be exactly one of: "CRITICAL", "URGENT", "HIGH", "NORMAL", "LOW", "IGNORE"
- required_tools: Array containing only valid tool actions: "calendar", "reminder", "task", "none"
- calendar_event: Null or object with title, start_time, end_time, description, attendees
- reminder: Null or object with title, due_date, priority, description
- task: Null or object with title, due_date, priority, description, assignees
- reasoning: String explaining your analysis and recommendations

Ensure all values match the expected types and formats. Return only serializable JSON object with no additional explanations."""

        try:
            # Create messages for OpenAI API
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": analysis_prompt}
            ]

            # Create a synchronous function to call the API
            def call_api():
                try:
                    return self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )
                except Exception as e:
                    self.logger.error(
                        f"API call error: {type(e).__name__}: {str(e)}")
                    return None

            # Use asyncio to run the API call
            async with self.semaphore:
                response = await asyncio.to_thread(call_api)

            # Check if response was successful
            if response is None:
                self.logger.error(
                    f"API call returned None for email: {email_data.get('subject', '')}")
                return None

            self.logger.info(
                f"API call successful for email: {email_data.get('subject', '')}")

            # Check if response has the expected structure
            if not hasattr(response, 'choices') or not response.choices:
                self.logger.error(f"Response has no choices: {response}")
                return None

            response_content = response.choices[0].message.content
            self.logger.debug(
                f"Response content length: {len(response_content) if response_content else 0}")

            # Clean and parse the JSON response
            cleaned_json_str = self._clean_json_response(response_content)
            self.logger.debug(
                f"Cleaned JSON length: {len(cleaned_json_str) if cleaned_json_str else 0}")

            # Parse the JSON with error handling
            try:
                result_json = json.loads(cleaned_json_str)
                # Create a structured result object
                result = EmailAnalysisResult(**result_json)

                self.logger.info(
                    f"Successfully parsed result for email: {email_data.get('subject', '')}")
                return {
                    'is_spam': result.is_spam,
                    'category': result.category,
                    'priority': result.priority,
                    'required_tools': result.required_tools,
                    'calendar_event': result.calendar_event,
                    'reminder': result.reminder,
                    'task': result.task,
                    'reasoning': result.reasoning
                }
            except json.JSONDecodeError as json_err:
                self.logger.error(f"JSON parsing error: {json_err}")
                self.logger.error(
                    f"Problematic JSON: {cleaned_json_str[:100]}...")
                return None
            except Exception as parse_err:
                self.logger.error(
                    f"Error parsing result: {type(parse_err).__name__}: {str(parse_err)}")
                return None
        except Exception as e:
            self.logger.exception(f"Error analyzing email: {str(e)}")
            return None

    async def analyze_email_batch(self, email_data_list: List[Dict[str, Any]], timezone: str = "America/Los_Angeles", batch_size: int = 2) -> List[Optional[Dict[str, Any]]]:
        """Analyze multiple emails concurrently.

        Args:
            email_data_list: List of dictionaries containing email information
            timezone: Timezone for date/time conversions
            batch_size: Number of emails to process in a batch

        Returns:
            List of dictionaries containing analysis results
        """
        results = []

        # Split the list into smaller batches
        for i in range(0, len(email_data_list), batch_size):
            batch = email_data_list[i:i+batch_size]
            self.logger.info(
                f"Processing batch {i//batch_size + 1} with {len(batch)} emails...")

            # Process this batch concurrently
            batch_tasks = [self.analyze_email(
                email_data, timezone) for email_data in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Handle exceptions and add results to the main list
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    self.logger.error(
                        f"Error processing email in batch: {str(result)}")
                    results.append(None)
                else:
                    results.append(result)

        return results
