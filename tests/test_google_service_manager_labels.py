import unittest

from email_fetcher.google_service_manager import GoogleServiceManager


class _DummyRequest:
    def __init__(self, callback):
        self._callback = callback

    def execute(self):
        return self._callback()


class _FakeLabelsApi:
    def __init__(self):
        self.create_calls = []
        self._labels = [
            {"id": "SYSTEM_SPAM", "name": "SPAM"},
            {"id": "LBL_PROCESSED", "name": "ProcessedByAgent"},
        ]

    def list(self, userId="me"):
        return _DummyRequest(lambda: {"labels": list(self._labels)})

    def create(self, userId="me", body=None):
        name = body["name"]
        self.create_calls.append(name)
        created = {"id": f"LBL_{len(self.create_calls)}", "name": name}
        self._labels.append(created)
        return _DummyRequest(lambda: created)


class _FakeUsersApi:
    def __init__(self, labels_api):
        self._labels_api = labels_api

    def labels(self):
        return self._labels_api


class _FakeGmailService:
    def __init__(self):
        self.labels_api = _FakeLabelsApi()

    def users(self):
        return _FakeUsersApi(self.labels_api)


class TestGoogleServiceManagerLabels(unittest.IsolatedAsyncioTestCase):
    async def test_maps_system_spam_without_creating_user_spam_label(self):
        manager = GoogleServiceManager()
        fake_gmail = _FakeGmailService()
        manager.services["default"] = {"gmail": fake_gmail}

        label_ids = await manager.setup_gmail_labels("default")

        self.assertIn("Spam", label_ids)
        self.assertEqual(label_ids["Spam"], "SYSTEM_SPAM")
        self.assertNotIn("Spam", fake_gmail.labels_api.create_calls)
        self.assertNotIn("SPAM", fake_gmail.labels_api.create_calls)

