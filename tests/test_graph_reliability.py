import asyncio
import unittest

from email_tagger import EmailTagger
from mail_agent.graph import build_graph, make_initial_state


class _DummyRequest:
    def __init__(self, callback):
        self._callback = callback

    def execute(self):
        self._callback()
        return {}


class _DummyMessages:
    def __init__(self, calls):
        self._calls = calls

    def modify(self, userId, id, body):
        return _DummyRequest(lambda: self._calls.append(("modify", id, body)))

    def trash(self, userId, id):
        return _DummyRequest(lambda: self._calls.append(("trash", id, None)))


class _DummyUsers:
    def __init__(self, calls):
        self._calls = calls

    def messages(self):
        return _DummyMessages(self._calls)


class _DummyService:
    def __init__(self, calls):
        self._calls = calls

    def users(self):
        return _DummyUsers(self._calls)


class _FakeFetcher:
    def __init__(self, sender_stats=None, sender_stats_error: bool = False):
        self.calls = []
        self.gmail_services = {"default": _DummyService(self.calls)}
        self.sender_stats = sender_stats or {
            "sender_unread_count_window": 0,
            "sender_overload": False,
        }
        self.sender_stats_error = sender_stats_error

    async def hydrate_attachment_content(self, account_id, message_id, attachments, max_bytes=None):
        return attachments

    async def get_sender_unread_window_stats(self, account_id, sender_email, days, threshold):
        if self.sender_stats_error:
            raise RuntimeError("stats unavailable")
        return dict(self.sender_stats)


class _FakePreprocessor:
    def preprocess_email(self, email_data):
        return {
            **email_data,
            "cleaned_body": "Cleaned body",
            "preprocessing_status": "success",
            "body_quality": "full_text",
            "text_length": 100,
        }


class _FakeAnalyzer:
    def __init__(self, analysis_result):
        self.analysis_result = analysis_result

    async def analyze_with_retry(self, input_data, timezone):
        return dict(self.analysis_result)


class _FakeCalendarAgent:
    async def create_event(self, event_details, account_id):
        return {"ok": True}

    async def create_reminder(self, title, due_date, priority=None, description=None, account_id="default"):
        return {"ok": True}

    async def create_task(self, task_details, account_id="default"):
        return {"ok": True}


async def _invoke_graph(app, state):
    if hasattr(app, "ainvoke"):
        return await app.ainvoke(state)
    return await asyncio.to_thread(app.invoke, state)


class TestGraphReliability(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_classification_not_processed(self):
        fetcher = _FakeFetcher()
        app = build_graph(
            preprocessor=_FakePreprocessor(),
            analyzer=_FakeAnalyzer(
                {
                    "is_spam": "NOT_SPAM",
                    "category": "WORK",
                    "required_tools": [],
                    "reasoning": "missing priority",
                    "classification_complete": False,
                    "classification_source": "llm_text",
                }
            ),
            calendar_agent=_FakeCalendarAgent(),
            tagger=EmailTagger(),
            fetcher=fetcher,
        )
        state = make_initial_state(
            {
                "id": "mail_1",
                "account_id": "default",
                "from": "boss@example.com",
                "subject": "Status",
                "date": "2026-02-10",
                "attachments": [],
            },
            {
                "ProcessedByAgent": "LBL_PROCESSED",
                "Priority/High": "LBL_PRIO_HIGH",
                "Category/Work": "LBL_CAT_WORK",
            },
            "UTC",
        )
        result = await _invoke_graph(app, state)
        self.assertFalse(result.get("processed", False))
        self.assertEqual(fetcher.calls, [])

    async def test_complete_non_spam_gets_processed_with_both_labels(self):
        fetcher = _FakeFetcher()
        app = build_graph(
            preprocessor=_FakePreprocessor(),
            analyzer=_FakeAnalyzer(
                {
                    "is_spam": "NOT_SPAM",
                    "category": "WORK",
                    "priority": "HIGH",
                    "required_tools": [],
                    "reasoning": "complete",
                    "classification_complete": True,
                    "classification_source": "llm_text",
                }
            ),
            calendar_agent=_FakeCalendarAgent(),
            tagger=EmailTagger(),
            fetcher=fetcher,
        )
        state = make_initial_state(
            {
                "id": "mail_2",
                "account_id": "default",
                "from": "boss@example.com",
                "subject": "Status",
                "date": "2026-02-10",
                "attachments": [],
            },
            {
                "ProcessedByAgent": "LBL_PROCESSED",
                "Priority/High": "LBL_PRIO_HIGH",
                "Category/Work": "LBL_CAT_WORK",
            },
            "UTC",
        )
        result = await _invoke_graph(app, state)
        self.assertTrue(result.get("processed", False))
        self.assertEqual(len(fetcher.calls), 1)
        action, message_id, body = fetcher.calls[0]
        self.assertEqual(action, "modify")
        self.assertEqual(message_id, "mail_2")
        self.assertIn("LBL_PROCESSED", body["addLabelIds"])
        self.assertIn("LBL_PRIO_HIGH", body["addLabelIds"])
        self.assertIn("LBL_CAT_WORK", body["addLabelIds"])

    async def test_spam_is_trashed_immediately(self):
        fetcher = _FakeFetcher()
        app = build_graph(
            preprocessor=_FakePreprocessor(),
            analyzer=_FakeAnalyzer(
                {
                    "is_spam": "SPAM",
                    "category": "MARKETING",
                    "priority": "IGNORE",
                    "required_tools": [],
                    "reasoning": "spam",
                    "classification_complete": True,
                    "classification_source": "llm_text",
                }
            ),
            calendar_agent=_FakeCalendarAgent(),
            tagger=EmailTagger(),
            fetcher=fetcher,
        )
        state = make_initial_state(
            {
                "id": "mail_3",
                "account_id": "default",
                "from": "spam@example.com",
                "subject": "You won",
                "date": "2026-02-10",
                "attachments": [],
            },
            {"ProcessedByAgent": "LBL_PROCESSED"},
            "UTC",
        )
        result = await _invoke_graph(app, state)
        self.assertTrue(result.get("processed", False))
        self.assertEqual(result.get("spam_disposition_status"), "trashed")
        self.assertEqual(fetcher.calls[0][0], "trash")

    async def test_spam_is_trashed_even_if_classification_incomplete(self):
        fetcher = _FakeFetcher()
        app = build_graph(
            preprocessor=_FakePreprocessor(),
            analyzer=_FakeAnalyzer(
                {
                    "is_spam": "SPAM",
                    "category": "MARKETING",
                    "required_tools": [],
                    "reasoning": "spam but missing priority",
                    "classification_complete": False,
                    "classification_source": "llm_text",
                }
            ),
            calendar_agent=_FakeCalendarAgent(),
            tagger=EmailTagger(),
            fetcher=fetcher,
        )
        state = make_initial_state(
            {
                "id": "mail_4",
                "account_id": "default",
                "from": "spam@example.com",
                "subject": "Claim prize",
                "date": "2026-02-10",
                "attachments": [],
            },
            {"ProcessedByAgent": "LBL_PROCESSED"},
            "UTC",
        )
        result = await _invoke_graph(app, state)
        self.assertTrue(result.get("processed", False))
        self.assertEqual(result.get("spam_disposition_status"), "trashed")
        self.assertEqual(fetcher.calls[0][0], "trash")

    async def test_sender_overload_forces_ignore_and_archives_read(self):
        fetcher = _FakeFetcher(
            sender_stats={"sender_unread_count_window": 12, "sender_overload": True}
        )
        app = build_graph(
            preprocessor=_FakePreprocessor(),
            analyzer=_FakeAnalyzer(
                {
                    "is_spam": "NOT_SPAM",
                    "category": "WORK",
                    "priority": "HIGH",
                    "required_tools": ["task"],
                    "task": {
                        "title": "Follow up",
                        "due_date": "2026-03-03T10:00:00Z",
                    },
                    "reasoning": "normal workload",
                    "classification_complete": True,
                    "classification_source": "llm_text",
                }
            ),
            calendar_agent=_FakeCalendarAgent(),
            tagger=EmailTagger(),
            fetcher=fetcher,
        )
        state = make_initial_state(
            {
                "id": "mail_overload",
                "account_id": "default",
                "from": "Sender <sender@example.com>",
                "sender_email": "sender@example.com",
                "subject": "Repeated updates",
                "date": "2026-02-10",
                "attachments": [],
            },
            {
                "ProcessedByAgent": "LBL_PROCESSED",
                "Priority/High": "LBL_PRIO_HIGH",
                "Priority/Ignore": "LBL_PRIO_IGNORE",
                "Category/Work": "LBL_CAT_WORK",
            },
            "UTC",
        )
        result = await _invoke_graph(app, state)

        self.assertTrue(result.get("processed", False))
        self.assertTrue(result.get("analysis", {}).get("priority_overridden_by_policy"))
        self.assertEqual(result.get("analysis", {}).get("priority"), "IGNORE")
        self.assertEqual(result.get("analysis", {}).get("required_tools"), [])
        self.assertEqual(len(fetcher.calls), 1)
        action, message_id, body = fetcher.calls[0]
        self.assertEqual(action, "modify")
        self.assertEqual(message_id, "mail_overload")
        self.assertIn("LBL_PROCESSED", body["addLabelIds"])
        self.assertIn("LBL_PRIO_IGNORE", body["addLabelIds"])
        self.assertIn("LBL_CAT_WORK", body["addLabelIds"])
        self.assertIn("UNREAD", body["removeLabelIds"])
        self.assertIn("INBOX", body["removeLabelIds"])

    async def test_sender_stats_failure_fails_open_without_override(self):
        fetcher = _FakeFetcher(sender_stats_error=True)
        app = build_graph(
            preprocessor=_FakePreprocessor(),
            analyzer=_FakeAnalyzer(
                {
                    "is_spam": "NOT_SPAM",
                    "category": "WORK",
                    "priority": "HIGH",
                    "required_tools": [],
                    "reasoning": "complete",
                    "classification_complete": True,
                    "classification_source": "llm_text",
                }
            ),
            calendar_agent=_FakeCalendarAgent(),
            tagger=EmailTagger(),
            fetcher=fetcher,
        )
        state = make_initial_state(
            {
                "id": "mail_fail_open",
                "account_id": "default",
                "from": "sender@example.com",
                "sender_email": "sender@example.com",
                "subject": "Status",
                "date": "2026-02-10",
                "attachments": [],
            },
            {
                "ProcessedByAgent": "LBL_PROCESSED",
                "Priority/High": "LBL_PRIO_HIGH",
                "Priority/Ignore": "LBL_PRIO_IGNORE",
                "Category/Work": "LBL_CAT_WORK",
            },
            "UTC",
        )
        result = await _invoke_graph(app, state)

        self.assertTrue(result.get("processed", False))
        self.assertFalse(result.get("analysis", {}).get("priority_overridden_by_policy", False))
        self.assertEqual(len(fetcher.calls), 1)
        _, _, body = fetcher.calls[0]
        self.assertIn("LBL_PRIO_HIGH", body["addLabelIds"])
        self.assertNotIn("removeLabelIds", body)
