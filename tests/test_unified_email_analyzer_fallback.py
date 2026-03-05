import asyncio
import logging
import unittest
from unittest.mock import AsyncMock

from spam_detector.unified_email_analyzer import (
    EmailCategory,
    EmailPriority,
    Spam,
    UnifiedEmailAnalyzer,
)


class TestUnifiedEmailAnalyzerFallback(unittest.IsolatedAsyncioTestCase):
    def _build_analyzer_without_init(self) -> UnifiedEmailAnalyzer:
        analyzer = UnifiedEmailAnalyzer.__new__(UnifiedEmailAnalyzer)
        analyzer.logger = logging.getLogger("test_unified_email_analyzer")
        analyzer.semaphore = asyncio.Semaphore(1)
        analyzer.system_prompt = "test prompt"
        analyzer.enable_multimodal_fallback = True
        analyzer.multimodal_max_attachments = 3
        analyzer.wait_for_rate_limit = AsyncMock()
        return analyzer

    async def test_multimodal_fallback_selected_for_short_body(self) -> None:
        analyzer = self._build_analyzer_without_init()
        analyzer._invoke_structured_analysis = AsyncMock(
            side_effect=[
                {
                    "is_spam": "NOT_SPAM",
                    "category": "WORK",
                    "required_tools": [],
                    "reasoning": "incomplete stage A",
                },
                {
                    "is_spam": "NOT_SPAM",
                    "category": "WORK",
                    "priority": "HIGH",
                    "required_tools": [],
                    "reasoning": "complete stage B",
                },
            ]
        )

        result = await UnifiedEmailAnalyzer.analyze_email(
            analyzer,
            {
                "from": "boss@example.com",
                "subject": "See attached",
                "received_date": "2026-02-10T12:00:00Z",
                "body": "pls see",
                "body_quality": "short_text",
                "has_non_text_content": True,
                "attachments": [
                    {
                        "mime_type": "image/png",
                        "data_b64": "aW1hZ2U=",
                        "filename": "image.png",
                    }
                ],
            },
            "UTC",
        )

        self.assertEqual(result["classification_source"], "llm_multimodal")
        self.assertTrue(result["classification_complete"])

    def test_heuristic_fallback_is_always_complete(self) -> None:
        analyzer = self._build_analyzer_without_init()
        result = UnifiedEmailAnalyzer._apply_heuristic_fallback(
            analyzer,
            {
                "from": "promo@example.com",
                "subject": "Huge discount - limited time offer",
                "body": "unsubscribe now",
            },
            reason="test fallback",
        )

        self.assertTrue(result["classification_complete"])
        self.assertIn(result["category"], {item.value for item in EmailCategory})
        self.assertIn(result["priority"], {item.value for item in EmailPriority})
        self.assertIn(result["is_spam"], {item.value for item in Spam})

    async def test_retry_returns_heuristic_on_final_failure(self) -> None:
        analyzer = self._build_analyzer_without_init()
        analyzer.rotate_api_key = lambda: False
        analyzer.analyze_email = AsyncMock(side_effect=RuntimeError("service unavailable"))

        result = await UnifiedEmailAnalyzer.analyze_with_retry(
            analyzer,
            {"from": "a@b.com", "subject": "hello", "body": "world"},
            timezone="UTC",
            max_retries=0,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["classification_source"], "heuristic")
        self.assertTrue(result["classification_complete"])

    def test_text_prompt_includes_sender_overload_context(self) -> None:
        analyzer = self._build_analyzer_without_init()
        prompt = UnifiedEmailAnalyzer._build_text_analysis_prompt(
            analyzer,
            {
                "from": "sender@example.com",
                "sender_email": "sender@example.com",
                "subject": "Hello",
                "received_date": "2026-03-01T10:00:00Z",
                "body": "Body",
                "body_quality": "full_text",
                "attachments": [],
                "sender_unread_count_window": 14,
                "sender_overload": True,
            },
            "UTC",
        )

        self.assertIn("Sender Email: sender@example.com", prompt)
        self.assertIn("Unread From Sender (", prompt)
        self.assertIn("): 14", prompt)
        self.assertIn("Sender Overload Flag: True", prompt)
