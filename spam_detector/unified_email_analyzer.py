"""Unified Email Analyzer module.

This module provides a unified interface for analyzing emails using different LLM backends.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Union
from enum import Enum, auto

# Try imports for different backends
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False


class ToolAction(Enum):
    """Enum for tool actions that can be taken on emails."""
    CALENDAR = "calendar"
    REMINDER = "reminder"
    TASK = "task"
    NONE = "none"


class UnifiedEmailAnalyzer:
    """Unified interface for analyzing emails using different backends."""

    def __init__(self, analyzer_type=None, backend=None):
        """Initialize the analyzer with the specified backend type.

        Args:
            analyzer_type: Legacy parameter name for backend type
            backend: Type of backend to use
        """
        # For backward compatibility, accept both analyzer_type and backend
        self.backend_type = backend or analyzer_type or os.environ.get(
            "MAIL_AGENT_ANALYZER", "openrouter")

        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Initializing UnifiedEmailAnalyzer with backend: {self.backend_type}")

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

    def _initialize_openrouter(self):
        """Initialize OpenRouter backend."""
        self.logger.info("Initializing OpenRouter backend")
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        if not self.openrouter_api_key:
            self.logger.error(
                "OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable.")
        else:
            self.logger.info("OpenRouter API key found")

    def _initialize_ollama(self):
        """Initialize Ollama backend."""
        self.logger.info("Initializing Ollama backend")
        if not OLLAMA_AVAILABLE:
            self.logger.error(
                "Ollama package not installed. Please install with 'pip install ollama'.")

    def _initialize_lmstudio(self):
        """Initialize LM Studio backend."""
        self.logger.info("Initializing LM Studio backend")
        self.lmstudio_url = os.environ.get(
            "LMSTUDIO_URL", "http://localhost:1234/v1")
        self.logger.info(f"Using LM Studio URL: {self.lmstudio_url}")

    def _initialize_groq(self):
        """Initialize Groq backend."""
        self.logger.info("Initializing Groq backend")
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        if not self.groq_api_key:
            self.logger.error(
                "Groq API key not found. Please set GROQ_API_KEY environment variable.")
        elif not GROQ_AVAILABLE:
            self.logger.error(
                "Groq package not installed. Please install with 'pip install groq'.")
        else:
            self.logger.info("Groq API key found")

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

        try:
            if self.backend_type == "openrouter":
                return await self._analyze_with_openrouter(email_data, timezone)
            elif self.backend_type == "ollama":
                return await self._analyze_with_ollama(email_data, timezone)
            elif self.backend_type == "lmstudio":
                return await self._analyze_with_lmstudio(email_data, timezone)
            elif self.backend_type == "groq":
                return await self._analyze_with_groq(email_data, timezone)
            else:
                self.logger.warning(
                    f"Unknown backend type: {self.backend_type}. Falling back to OpenRouter.")
                return await self._analyze_with_openrouter(email_data, timezone)
        except Exception as e:
            self.logger.exception(f"Error analyzing email: {str(e)}")
            return None

    async def _analyze_with_openrouter(self, email_data: Dict[str, Any], timezone: str) -> Optional[Dict[str, Any]]:
        """Analyze an email using OpenRouter."""
        if not self.openrouter_api_key:
            self.logger.error("OpenRouter API key not set")
            return None

        self.logger.info("Using OpenRouter for analysis")

        # Implement OpenRouter analysis logic
        # This is a placeholder - you'll need to implement the actual API call

        # Return sample data for testing
        return {
            "is_spam": False,
            "category": "WORK",
            "priority": "NORMAL",
            "required_tools": [],
            "reasoning": "This is a test email for health check"
        }

    async def _analyze_with_ollama(self, email_data: Dict[str, Any], timezone: str) -> Optional[Dict[str, Any]]:
        """Analyze an email using Ollama."""
        self.logger.info("Using Ollama for analysis")

        # Implement Ollama analysis logic
        # This is a placeholder

        return {
            "is_spam": False,
            "category": "WORK",
            "priority": "NORMAL",
            "required_tools": [],
            "reasoning": "This is a test email for health check"
        }

    async def _analyze_with_lmstudio(self, email_data: Dict[str, Any], timezone: str) -> Optional[Dict[str, Any]]:
        """Analyze an email using LM Studio."""
        self.logger.info("Using LM Studio for analysis")

        # Implement LM Studio analysis logic
        # This is a placeholder

        return {
            "is_spam": False,
            "category": "WORK",
            "priority": "NORMAL",
            "required_tools": [],
            "reasoning": "This is a test email for health check"
        }

    async def _analyze_with_groq(self, email_data: Dict[str, Any], timezone: str) -> Optional[Dict[str, Any]]:
        """Analyze an email using Groq."""
        if not self.groq_api_key:
            self.logger.error("Groq API key not set")
            return None

        self.logger.info("Using Groq for analysis")

        # Implement Groq analysis logic
        # This is a placeholder

        return {
            "is_spam": False,
            "category": "WORK",
            "priority": "NORMAL",
            "required_tools": [],
            "reasoning": "This is a test email for health check"
        }
