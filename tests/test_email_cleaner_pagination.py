import unittest

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
        return _DummyRequest(
            {
                "id": id,
                "labelIds": ["LBL_PROCESSED"],
                "payload": {
                    "headers": [
                        {"name": "Date", "value": "Tue, 10 Feb 2026 10:00:00 +0000"}
                    ]
                },
                "internalDate": "1739181600000",
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


class TestEmailCleanerPagination(unittest.IsolatedAsyncioTestCase):
    async def test_get_emails_for_cleanup_paginates_all_pages(self):
        fetcher = _FakeFetcher()
        cleaner = EmailCleaner(fetcher)

        emails = await cleaner.get_emails_for_cleanup("default")

        self.assertEqual([email["id"] for email in emails], ["m1", "m2"])
        self.assertEqual(
            fetcher.gmail_services["default"].messages_api.page_tokens,
            [None, "page-2"],
        )

