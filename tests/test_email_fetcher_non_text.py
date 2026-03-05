import base64
import unittest
from unittest.mock import AsyncMock

from email_fetcher import EmailFetcher


class _DummyRequest:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeMessagesApi:
    def __init__(self):
        self.main_list_calls = []
        self.sender_list_calls = []
        self.sender_query_call_count = 0

    def list(self, userId="me", q=None, pageToken=None, maxResults=None):
        query = q or ""
        if "from:sender@example.com" in query:
            self.sender_query_call_count += 1
            self.sender_list_calls.append(pageToken)
            if pageToken is None:
                return _DummyRequest(
                    {
                        "messages": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}, {"id": "s4"}],
                        "nextPageToken": "s-page-2",
                    }
                )
            if pageToken == "s-page-2":
                return _DummyRequest(
                    {
                        "messages": [{"id": "s5"}, {"id": "s6"}, {"id": "s7"}],
                    }
                )
            return _DummyRequest({})

        self.main_list_calls.append(pageToken)
        if pageToken is None:
            return _DummyRequest(
                {
                    "messages": [{"id": "m1"}],
                    "nextPageToken": "page-2",
                }
            )
        if pageToken == "page-2":
            return _DummyRequest({"messages": [{"id": "m2"}]})
        return _DummyRequest({})

    def get(self, userId="me", id=None, format="full"):
        if id == "m1":
            payload = {
                "id": "m1",
                "threadId": "t1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Subject 1"},
                        {"name": "From", "value": "Alice Example <Alice@example.COM>"},
                        {"name": "Date", "value": "Mon, 01 Mar 2026 10:00:00 +0000"},
                    ],
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"hello").decode("utf-8"),
                    },
                },
            }
            return _DummyRequest(payload)
        payload = {
            "id": "m2",
            "threadId": "t2",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Subject 2"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Date", "value": "Mon, 01 Mar 2026 11:00:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(b"world").decode("utf-8"),
                },
            },
        }
        return _DummyRequest(payload)

    def attachments(self):
        return self


class _FakeUsersApi:
    def __init__(self):
        self._messages = _FakeMessagesApi()

    def messages(self):
        return self._messages


class _FakeGmailService:
    def __init__(self):
        self._users = _FakeUsersApi()

    def users(self):
        return self._users


class TestEmailFetcherNonText(unittest.IsolatedAsyncioTestCase):
    def test_extracts_non_text_attachments(self) -> None:
        fetcher = EmailFetcher()
        text_b64 = base64.urlsafe_b64encode(b"hello world").decode("utf-8")
        pdf_inline_b64 = base64.urlsafe_b64encode(b"pdf data").decode("utf-8")
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": text_b64}},
                {
                    "mimeType": "image/png",
                    "filename": "chart.png",
                    "body": {"attachmentId": "att_1", "size": 128},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "invoice.pdf",
                    "body": {"data": pdf_inline_b64, "size": 256},
                },
            ],
        }

        body, attachments, has_non_text = fetcher._extract_email_content(payload)
        self.assertEqual(body, text_b64)
        self.assertTrue(has_non_text)
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0]["mime_type"], "image/png")
        self.assertEqual(attachments[1]["mime_type"], "application/pdf")

    async def test_hydrates_attachment_content(self) -> None:
        fetcher = EmailFetcher()
        fetcher.fetch_attachment_bytes = AsyncMock(return_value=b"binary-attachment")
        inline_b64 = base64.urlsafe_b64encode(b"inline-bytes").decode("utf-8")

        hydrated = await fetcher.hydrate_attachment_content(
            account_id="default",
            message_id="msg_1",
            attachments=[
                {
                    "attachment_id": "att_2",
                    "filename": "pic.jpg",
                    "mime_type": "image/jpeg",
                    "size": 10,
                    "inline_data_b64": None,
                },
                {
                    "attachment_id": None,
                    "filename": "inline.pdf",
                    "mime_type": "application/pdf",
                    "size": 10,
                    "inline_data_b64": inline_b64,
                },
            ],
        )

        self.assertEqual(len(hydrated), 2)
        self.assertTrue(hydrated[0].get("data_b64"))
        self.assertTrue(hydrated[1].get("data_b64"))

    async def test_fetch_gmail_emails_paginates_and_parses_sender_email(self) -> None:
        fetcher = EmailFetcher()
        fake_service = _FakeGmailService()
        fetcher.gmail_services = {"default": fake_service}

        emails = await fetcher.fetch_gmail_emails()

        self.assertEqual([email["id"] for email in emails], ["m1", "m2"])
        self.assertEqual(
            fake_service.users().messages().main_list_calls,
            [None, "page-2"],
        )
        self.assertEqual(emails[0]["sender_email"], "alice@example.com")
        self.assertEqual(emails[1]["sender_email"], "sender@example.com")

    async def test_sender_unread_window_stats_threshold_and_cache(self) -> None:
        fetcher = EmailFetcher()
        fake_service = _FakeGmailService()
        fetcher.gmail_services = {"default": fake_service}

        first = await fetcher.get_sender_unread_window_stats(
            account_id="default",
            sender_email="sender@example.com",
            days=30,
            threshold=6,
        )
        second = await fetcher.get_sender_unread_window_stats(
            account_id="default",
            sender_email="sender@example.com",
            days=30,
            threshold=6,
        )

        self.assertEqual(first["sender_unread_count_window"], 7)
        self.assertTrue(first["sender_overload"])
        self.assertEqual(second, first)
        self.assertEqual(fake_service.users().messages().sender_query_call_count, 2)
