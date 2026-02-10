import unittest

from email_tagger import EmailTagger


class TestEmailTaggerStrict(unittest.IsolatedAsyncioTestCase):
    async def test_requires_both_priority_and_category(self) -> None:
        tagger = EmailTagger()
        result = await tagger.tag_email(
            {"id": "mail_1"},
            {"is_spam": "NOT_SPAM", "category": "WORK"},
        )
        self.assertEqual(result.get("tagging_status"), "error")
        self.assertIn("Missing required classification fields", result.get("error_message", ""))

    async def test_success_when_both_tags_present(self) -> None:
        tagger = EmailTagger()
        result = await tagger.tag_email(
            {"id": "mail_2"},
            {"is_spam": "NOT_SPAM", "category": "WORK", "priority": "HIGH"},
        )
        self.assertEqual(result.get("tagging_status"), "success")
        self.assertIn("Priority/High", result.get("tags", []))
        self.assertIn("Category/Work", result.get("tags", []))
