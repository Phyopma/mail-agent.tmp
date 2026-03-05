import base64
import unittest

from email_preprocessor import EmailPreprocessor


def _encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8")


class TestEmailPreprocessorExtraction(unittest.TestCase):
    def test_reply_chain_removed_and_flagged(self) -> None:
        preprocessor = EmailPreprocessor()
        body = (
            "Hello team,\n"
            "Please see updates below.\n\n"
            "On Tue, Mar 1, 2026 at 9:00 AM Bob <bob@example.com> wrote:\n"
            "> old reply content\n"
            "-----Original Message-----\n"
            "From: legacy@example.com\n"
        )
        result = preprocessor.preprocess_email({"body": _encode(body)})

        self.assertEqual(result["preprocessing_status"], "success")
        self.assertTrue(result["has_reply_chain"])
        self.assertNotIn("On Tue, Mar 1, 2026", result["cleaned_body"])
        self.assertNotIn("Original Message", result["cleaned_body"])

    def test_url_placeholder_preserves_signal(self) -> None:
        preprocessor = EmailPreprocessor()
        result = preprocessor.preprocess_email(
            {"body": _encode("Review https://example.com/path and www.test.com now")}
        )

        self.assertEqual(result["preprocessing_status"], "success")
        self.assertIn("[URL]", result["cleaned_body"])
        self.assertNotIn("https://example.com/path", result["cleaned_body"])
        self.assertNotIn("www.test.com", result["cleaned_body"])

    def test_extraction_source_defaults_to_none_when_body_missing(self) -> None:
        preprocessor = EmailPreprocessor()
        result = preprocessor.preprocess_email({})

        self.assertEqual(result["preprocessing_status"], "success")
        self.assertEqual(result["extraction_source"], "none")
        self.assertFalse(result["has_reply_chain"])
