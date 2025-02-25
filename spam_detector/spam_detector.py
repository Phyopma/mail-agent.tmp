"""Spam Detection Module for Mail Agent.

This module uses a local LLM (Llama) through Ollama to detect spam emails.
It provides structured output and integrates with the email preprocessing pipeline.
"""

from typing import Dict, Any, Optional, List
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import json
import asyncio


class SpamDetectionResult(BaseModel):
    """Structured output for spam detection results."""
    is_spam: bool = Field(
        description="Whether the email is classified as spam")
    confidence: float = Field(description="Confidence score between 0 and 1")
    reasoning: str = Field(description="Explanation for the classification")


class SpamDetector:
    """Handles spam detection using local LLM through Ollama."""

    def __init__(self, model_name: str = "llama3.1:8b-instruct-q4_K_M", max_concurrent_requests: int = 3):
        """Initialize the spam detector.

        Args:
            model_name: Name of the Ollama model to use
            max_concurrent_requests: Maximum number of concurrent requests to Ollama
        """
        self.llm = OllamaLLM(model=model_name, temperature=0)
        self.output_parser = PydanticOutputParser(
            pydantic_object=SpamDetectionResult)
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

        # System prompt for spam detection
        self.system_prompt = """
        You are an expert email spam detector. Your task is to analyze emails and determine if they are spam.
        Consider these characteristics of spam emails:
        1. Unsolicited commercial content or marketing materials
        2. Suspicious sender addresses (mismatched domains, random characters)
        3. Poor grammar, spelling errors, or unusual formatting
        4. Urgency or pressure tactics ("Act now!", "Limited time")
        5. Requests for sensitive information (passwords, bank details)
        6. Too-good-to-be-true offers (prizes, inheritance, investments)
        7. Excessive use of capital letters, punctuation, or emojis
        8. Generic greetings ("Dear Sir/Madam", "Dear User")
        9. Mismatched sender name and email address
        10. Links to suspicious or shortened URLs
        11. Requests for money transfers or cryptocurrency
        12. Impersonation of legitimate organizations

        Analyze the email holistically and provide your analysis in a structured format with:
        - A boolean indicating if it's spam (true/false)
        - A confidence score between 0 and 1 (higher = more confident) independent of the boolean
        - Clear, brief reasoning explaining your classification based on the above characteristics
        """

        self.prompt_template = PromptTemplate(
            template="{system_prompt}\n\nAnalyze this email:\nFrom: {from_address}\nSubject: {subject}\nBody:\n{body}\n\n{format_instructions}",
            input_variables=["from_address", "subject", "body"],
            partial_variables={
                "system_prompt": self.system_prompt,
                "format_instructions": self.output_parser.get_format_instructions()
            }
        )

    async def detect_spam(self, email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect if an email is spam using the local LLM.

        Args:
            email_data: Dictionary containing email information

        Returns:
            Dictionary containing spam detection results
        """
        try:
            # Prepare the prompt
            prompt = self.prompt_template.format(
                from_address=email_data.get('from', ''),
                subject=email_data.get('subject', ''),
                body=email_data.get('body', '')
            )

            # Get response from LLM
            llm_response = await self.llm.agenerate([prompt])
            response_text = llm_response.generations[0][0].text

            # Parse the response
            result = self.output_parser.parse(response_text)

            return {
                'is_spam': result.is_spam,
                'confidence': result.confidence,
                'reasoning': result.reasoning
            }

        except Exception as e:
            print(f"Error during spam detection: {str(e)}")
            return None

    async def detect_spam_batch(self, email_data_list: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
        """Detect spam in multiple emails concurrently.

        Args:
            email_data_list: List of dictionaries containing email information

        Returns:
            List of dictionaries containing spam detection results
        """
        async def process_single_email(email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with self.semaphore:
                return await self.detect_spam(email_data)

        tasks = [process_single_email(email_data)
                 for email_data in email_data_list]
        return await asyncio.gather(*tasks)

    def update_system_prompt(self, new_prompt: str) -> None:
        """Update the system prompt used for spam detection.

        Args:
            new_prompt: New system prompt to use
        """
        self.system_prompt = new_prompt
        self.prompt_template = PromptTemplate(
            template="{system_prompt}\n\nAnalyze this email:\nFrom: {from_address}\nSubject: {subject}\nBody:\n{body}\n\n{format_instructions}",
            input_variables=["from_address", "subject", "body"],
            partial_variables={
                "system_prompt": self.system_prompt,
                "format_instructions": self.output_parser.get_format_instructions()
            }
        )
