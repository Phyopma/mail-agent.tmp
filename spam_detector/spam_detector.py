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

class EmailAnalysisResult(BaseModel):
    """Structured output for email analysis following OpenAI guidelines."""
    is_spam: Spam = Field(
        description="Classifies the email as SPAM or NOT_SPAM based on comprehensive analysis of sender patterns, content characteristics, and red flags. Consider factors like suspicious domains, urgency tactics, unsolicited offers, and requests for sensitive information.")

    category: EmailCategory = Field(
        description="Determines the primary category (WORK/PERSONAL/FAMILY/SOCIAL/MARKETING/SCHOOL/NEWSLETTER/SHOPPING) based on sender relationship, content context, communication style, and purpose. Analyzes tone, formatting, domain, and specific content indicators unique to each category.")
    priority: EmailPriority = Field(
        description="Assigns priority level (CRITICAL/URGENT/HIGH/NORMAL/LOW/IGNORE) based on time sensitivity, impact, and required action. Considers explicit deadlines, business impact, emergency nature, and whether a response is needed.")
    # action_items: PyList[EmailAction] = Field(
    #     description="List of required actions from the email")
    # suggested_tools: PyList[EmailTool] = Field(
    #     description="List of relevant tools for the actions")


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
                max_tokens=6000,
                callbacks=None  # Disable LangSmith tracking
            )
        else:  # lmstudio
            self.llm = ChatOpenAI(
                base_url="http://localhost:1234/v1",  # Default LMStudio port
                # api_key="not-needed",
                # model_name="lmstudio-community/Qwen2.5-14B-Instruct-1M-GGUF",
                # model_name="qwen2.5-14b-instruct-1m",
                model_name="meta-llama-3.1-8b-instruct",
                temperature=0,
                max_tokens=6000
            )

        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

        # Optimized system prompt following OpenAI guidelines
        self.system_prompt = """
        You are an expert email analyzer specializing in spam detection, categorization, and priority assessment.
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

        Provide your analysis in a structured format with:
        1. Spam classification (SPAM/NOT_SPAM) - based on comprehensive spam indicators
        2. Email category (WORK/PERSONAL/FAMILY/SOCIAL/MARKETING/SCHOOL/NEWSLETTER/SHOPPING) - based on content and context analysis
        3. Priority level (CRITICAL/URGENT/HIGH/NORMAL/LOW/IGNORE) - based on time sensitivity and impact
        """

    async def analyze_email(self, email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
            analysis_prompt = f"""Analyze this email and provide a structured analysis: From: {email_data.get('from', '')}Subject: {email_data.get('subject', '')} Body:{email_data.get('body', '')}"""

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
                # 'confidence': result.spam_confidence,
                # 'reasoning': result.spam_reasoning
                'category': result.category,
                'priority': result.priority
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


# class SpamDetectionResult(BaseModel):
#     """Structured output for spam detection results."""
#     is_spam: bool=Field(
#         description="Whether the email is classified as spam")
#     confidence: float=Field(description="Confidence score between 0 and 1")
#     reasoning: str=Field(description="Explanation for the classification")


# class SpamDetector:
#     """Handles spam detection using local LLM through Ollama."""

#     def __init__(self, model_name: str="llama3.1:8b-instruct-q4_K_M", max_concurrent_requests: int=3):
#         """Initialize the spam detector.

#         Args:
#             model_name: Name of the Ollama model to use
#             max_concurrent_requests: Maximum number of concurrent requests to Ollama
#         """
#         self.llm=ChatOpenAI(
#             base_url="http://localhost:11434/v1",
#             api_key="not-needed",
#             temperature=0,
#             max_tokens=2048,
#             model_name=model_name
#         )
#         self.output_parser=PydanticOutputParser(
#             pydantic_object=SpamDetectionResult)
#         self.semaphore=asyncio.Semaphore(max_concurrent_requests)

#         # System prompt for spam detection
#         self.system_prompt="""
#         You are an expert email spam detector. Your task is to analyze emails and determine if they are spam.
#         Consider these characteristics of spam emails:
#         1. Unsolicited commercial content or marketing materials
#         2. Suspicious sender addresses (mismatched domains, random characters)
#         3. Poor grammar, spelling errors, or unusual formatting
#         4. Urgency or pressure tactics ("Act now!", "Limited time")
#         5. Requests for sensitive information (passwords, bank details)
#         6. Too-good-to-be-true offers (prizes, inheritance, investments)
#         7. Excessive use of capital letters, punctuation, or emojis
#         8. Generic greetings ("Dear Sir/Madam", "Dear User")
#         9. Mismatched sender name and email address
#         10. Links to suspicious or shortened URLs
#         11. Requests for money transfers or cryptocurrency
#         12. Impersonation of legitimate organizations

#         Analyze the email holistically and provide your analysis in a structured format with:
#         - A boolean indicating if it's spam (true/false)
#         - A confidence score between 0 and 1 (higher = more confident) independent of the boolean
#         - Clear, brief reasoning explaining your classification based on the above characteristics
#         """

#         self.prompt_template=PromptTemplate(
#             template="{system_prompt}\n\nAnalyze this email:\nFrom: {from_address}\nSubject: {subject}\nBody:\n{body}\n\n{format_instructions}",
#             input_variables=["from_address", "subject", "body"],
#             partial_variables={
#                 "system_prompt": self.system_prompt,
#                 "format_instructions": self.output_parser.get_format_instructions()
#             }
#         )

#     async def detect_spam(self, email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
#         """Detect if an email is spam using the local LLM.

#         Args:
#             email_data: Dictionary containing email information

#         Returns:
#             Dictionary containing spam detection results
#         """
#         try:
#             # Prepare the prompt
#             prompt=self.prompt_template.format(
#                 from_address=email_data.get('from', ''),
#                 subject=email_data.get('subject', ''),
#                 body=email_data.get('body', '')
#             )

#             # Get response from LLM
#             llm_response=await self.llm.agenerate([prompt])
#             response_text=llm_response.generations[0][0].text

#             # Parse the response
#             result=self.output_parser.parse(response_text)

#             return {
#                 'is_spam': result.is_spam,
#                 'confidence': result.confidence,
#                 'reasoning': result.reasoning
#             }

#         except Exception as e:
#             print(f"Error during spam detection: {str(e)}")
#             return None

#     async def detect_spam_batch(self, email_data_list: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
#         """Detect spam in multiple emails concurrently.

#         Args:
#             email_data_list: List of dictionaries containing email information

#         Returns:
#             List of dictionaries containing spam detection results
#         """
#         async def process_single_email(email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
#             async with self.semaphore:
#                 return await self.detect_spam(email_data)

#         tasks=[process_single_email(email_data)
#                  for email_data in email_data_list]
#         return await asyncio.gather(*tasks)
