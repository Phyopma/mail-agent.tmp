import base64
import unittest
from unittest.mock import AsyncMock

from email_fetcher import EmailFetcher


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
