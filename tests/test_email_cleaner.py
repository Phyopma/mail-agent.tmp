import unittest
from unittest.mock import patch

from mail_agent.email_cleaner import EmailCleaner


class _DummyRequest:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeLabelsApi:
    def list(self, userId="me"):
        return _DummyRequest(
            {
                "labels": [
                    {"id": "LBL_PROCESSED", "name": "ProcessedByAgent"},
                    {"id": "LBL_SPAM", "name": "SPAM"},
                ]
            }
        )


class _FakeMessagesApi:
    def __init__(self):
        self.page_tokens = []

    def list(self, userId="me", q=None, maxResults=500, pageToken=None):
        self.page_tokens.append(pageToken)
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

    def get(self, userId="me", id=None, format="metadata", metadataHeaders=None):
        if id == "m1":
            return _DummyRequest(
                {
                    "id": "m1",
                    "labelIds": ["LBL_PROCESSED"],
                    "payload": {"headers": [{"name": "Date", "value": "Tue, 10 Feb 2026 10:00:00 +0000"}]},
                    "internalDate": "1739181600000",
                }
            )
        return _DummyRequest(
            {
                "id": "m2",
                "labelIds": ["LBL_PROCESSED", "LBL_SPAM"],
                "payload": {"headers": [{"name": "Date", "value": "Tue, 10 Feb 2026 11:00:00 +0000"}]},
                "internalDate": "1739185200000",
            }
        )


class _FakeUsersApi:
    def __init__(self, messages_api):
        self._messages_api = messages_api
        self._labels_api = _FakeLabelsApi()

    def messages(self):
        return self._messages_api

    def labels(self):
        return self._labels_api


class _FakeGmailService:
    def __init__(self):
        self.messages_api = _FakeMessagesApi()
        self.users_api = _FakeUsersApi(self.messages_api)

    def users(self):
        return self.users_api


class _FakeFetcher:
    def __init__(self):
        self.gmail_services = {"default": _FakeGmailService()}


class TestEmailCleaner(unittest.IsolatedAsyncioTestCase):
    async def test_get_emails_for_cleanup_paginates_all_pages(self):
        fetcher = _FakeFetcher()
        cleaner = EmailCleaner(fetcher)

        emails = await cleaner.get_emails_for_cleanup("default")

        self.assertEqual([e["id"] for e in emails], ["m1", "m2"])
        self.assertEqual(fetcher.gmail_services["default"].messages_api.page_tokens, [None, "page-2"])

    async def test_spam_failsafe_is_case_insensitive(self):
        cleaner = EmailCleaner(_FakeFetcher())
        self.assertTrue(cleaner._has_spam_label(["SPAM"]))
        self.assertTrue(cleaner._has_spam_label(["Spam"]))
        self.assertTrue(cleaner._has_spam_label(["spam"]))

    async def test_run_cleanup_deletes_uppercase_spam_label(self):
        fetcher = _FakeFetcher()
        cleaner = EmailCleaner(fetcher)

        async def _fake_get_emails(account_id):
            return [{"id": "m-spam", "account_id": account_id, "labels": ["SPAM"], "internal_date": "1739185200000"}]

        deleted_ids = []

        async def _fake_delete(account_id, email_id, dry_run=False):
            deleted_ids.append(email_id)
            return True

        cleaner.get_emails_for_cleanup = _fake_get_emails
        cleaner.delete_email = _fake_delete

        with patch("mail_agent.email_cleaner.config.get", return_value=True):
            result = await cleaner.run_cleanup(dry_run=False)

        self.assertEqual(deleted_ids, ["m-spam"])
        self.assertEqual(result["deleted"], 1)

