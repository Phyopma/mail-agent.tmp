import unittest
from unittest.mock import patch

from mail_agent.email_cleaner import EmailCleaner


class _FakeFetcher:
    def __init__(self):
        # run_cleanup iterates keys; we only need one account id for mocked methods.
        self.gmail_services = {"default": object()}


class TestEmailCleanerSpamCasing(unittest.IsolatedAsyncioTestCase):
    async def test_spam_failsafe_is_case_insensitive(self):
        cleaner = EmailCleaner(_FakeFetcher())
        self.assertTrue(cleaner._has_spam_label(["SPAM"]))
        self.assertTrue(cleaner._has_spam_label(["Spam"]))
        self.assertTrue(cleaner._has_spam_label(["spam"]))

    async def test_run_cleanup_deletes_uppercase_spam_label(self):
        cleaner = EmailCleaner(_FakeFetcher())

        async def _fake_get_emails(account_id):
            return [
                {
                    "id": "m-spam",
                    "account_id": account_id,
                    "labels": ["SPAM"],
                    "internal_date": "1739185200000",
                }
            ]

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

