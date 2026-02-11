"""Email Fetcher Module for Mail Agent.

This module handles fetching unprocessed emails from Gmail accounts.
It supports async operations and provides a standardized output format for LangGraph.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import base64
from email_fetcher.google_service_manager import GoogleServiceManager


class EmailFetcher:
    """Handles fetching emails from Gmail."""

    def __init__(self):
        self.service_manager = GoogleServiceManager()
        self.processed_tag = "ProcessedByAgent"
        self.gmail_services = {}
        self.label_ids = {}

    async def setup_gmail(self, credentials_path: str, token_path: str, account_id: str = 'default') -> None:
        """Setup Gmail API client.

        Args:
            credentials_path: Path to the Gmail API credentials file
            token_path: Path to save/load the Gmail token
            account_id: Unique identifier for this account
        """
        services = await self.service_manager.setup_services(credentials_path, token_path, account_id)
        self.gmail_services[account_id] = services['gmail']

        # Setup labels for this account
        self.label_ids[account_id] = await self.service_manager.setup_gmail_labels(account_id)

    async def fetch_gmail_emails(self) -> List[Dict[str, Any]]:
        """Fetch unprocessed emails from Gmail within the last 24 hours.

        Filters out:
        - Emails with the ProcessedByAgent label
        - Emails received before 1 day ago

        Returns:
            List of standardized email objects
        """
        if not self.gmail_services:
            raise ValueError(
                "No Gmail services initialized. Call setup_gmail() first.")

        all_emails = []
        yesterday = (datetime.utcnow() - timedelta(days=1)
                     ).strftime('%Y/%m/%d')

        for account_id, gmail_service in self.gmail_services.items():
            print(f"Fetching Gmail emails for account {account_id}...")
            # Query to filter emails:
            # - after:yesterday - only emails from the last 24 hours
            # - -label:ProcessedByAgent - exclude emails already processed
            query = f"after:{yesterday} -label:{self.processed_tag}"

            try:
                results = await asyncio.to_thread(
                    gmail_service.users().messages().list(userId='me', q=query).execute
                )
                messages = results.get('messages', [])

                for i, message in enumerate(messages):

                    if i > 0 and i % 5 == 0:  # Every 5 messages instead of 10
                        print(
                            f"Pausing for rate limit... ({i}/{len(messages)})")
                        await asyncio.sleep(2)
                    msg = await asyncio.to_thread(
                        gmail_service.users().messages().get(
                            userId='me', id=message['id'], format='full'
                        ).execute
                    )

                    payload = msg.get('payload', {})
                    headers = payload.get('headers', [])
                    body, attachments, has_non_text_content = self._extract_email_content(
                        payload
                    )
                    email_data = {
                        'id': msg['id'],
                        'provider': 'gmail',
                        'account_id': account_id,
                        'subject': self._get_header_value(headers, 'subject'),
                        'from': self._get_header_value(headers, 'from'),
                        'date': self._get_header_value(headers, 'date'),
                        'body': body,
                        'attachments': attachments,
                        'has_non_text_content': has_non_text_content,
                        'thread_id': msg['threadId']
                    }
                    all_emails.append(email_data)
            except Exception as e:
                print(
                    f"Error fetching Gmail emails for account {account_id}: {str(e)}")

        return all_emails

    def _get_header_value(self, headers: List[Dict[str, Any]], name: str) -> str:
        """Get a specific header value from Gmail payload headers."""
        for header in headers:
            if header.get('name', '').lower() == name:
                return header.get('value', '')
        return ''

    def _extract_email_content(
        self, payload: Dict[str, Any]
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """Extract the best text body and non-text attachment metadata.

        Returns:
            Tuple of (body_base64, attachments, has_non_text_content)
        """
        body = self._get_email_body(payload)
        attachments: List[Dict[str, Any]] = []
        self._collect_attachments(payload, attachments)

        # De-duplicate attachment entries coming from nested MIME parts.
        deduped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for attachment in attachments:
            key = (
                attachment.get('attachment_id') or '',
                attachment.get('filename') or '',
                attachment.get('mime_type') or '',
            )
            if key not in deduped:
                deduped[key] = attachment
        attachment_list = list(deduped.values())

        return body, attachment_list, bool(attachment_list)

    def _get_email_body(self, payload: Dict[str, Any]) -> str:
        """Extract email body from Gmail message payload.

        Args:
            payload: Gmail message payload

        Returns:
            Extracted email body text
        """
        if 'parts' in payload:
            text_plain = self._find_part_by_mime(payload['parts'], 'text/plain')
            if text_plain:
                return text_plain

            text_html = self._find_part_by_mime(payload['parts'], 'text/html')
            if text_html:
                return text_html

        if 'body' in payload and payload['body'].get('data'):
            return payload['body']['data']

        return ""

    def _find_part_by_mime(self, parts: List[Dict[str, Any]], mime_type: str) -> Optional[str]:
        """Recursively find the first part matching a MIME type."""
        for part in parts:
            if part.get('mimeType') == mime_type and part.get('body', {}).get('data'):
                return part['body']['data']
            if part.get('parts'):
                nested = self._find_part_by_mime(part['parts'], mime_type)
                if nested:
                    return nested
        return None

    def _is_non_text_mime(self, mime_type: str) -> bool:
        """Return True when MIME type indicates non-text content."""
        if not mime_type:
            return False
        lowered = mime_type.lower()
        if lowered.startswith("multipart/"):
            return False
        return not lowered.startswith("text/")

    def _collect_attachments(
        self, part: Dict[str, Any], attachments: List[Dict[str, Any]]
    ) -> None:
        """Recursively collect non-text attachment and inline part metadata."""
        mime_type = part.get('mimeType', '')
        body = part.get('body', {}) or {}
        filename = part.get('filename') or ''
        attachment_id = body.get('attachmentId')
        inline_data_b64 = body.get('data')
        size = body.get('size', 0)

        if self._is_non_text_mime(mime_type):
            if attachment_id or inline_data_b64 or filename:
                attachments.append(
                    {
                        'attachment_id': attachment_id,
                        'filename': filename,
                        'mime_type': mime_type,
                        'size': size,
                        'inline_data_b64': inline_data_b64,
                    }
                )

        for child in part.get('parts', []) or []:
            self._collect_attachments(child, attachments)

    @staticmethod
    def _urlsafe_b64_to_bytes(data: str) -> bytes:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))

    async def fetch_attachment_bytes(
        self,
        account_id: str,
        message_id: str,
        attachment_id: str,
    ) -> Optional[bytes]:
        """Fetch attachment bytes from Gmail by attachment ID."""
        gmail_service = self.gmail_services.get(account_id)
        if not gmail_service:
            return None

        try:
            attachment = await asyncio.to_thread(
                gmail_service.users()
                .messages()
                .attachments()
                .get(userId='me', messageId=message_id, id=attachment_id)
                .execute
            )
            data = attachment.get("data")
            if not data:
                return None
            return self._urlsafe_b64_to_bytes(data)
        except Exception as e:
            print(
                f"Error fetching attachment {attachment_id} for message {message_id}: {str(e)}"
            )
            return None

    async def hydrate_attachment_content(
        self,
        account_id: str,
        message_id: str,
        attachments: List[Dict[str, Any]],
        max_bytes: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Hydrate non-text attachments with base64 content for multimodal analysis."""
        hydrated: List[Dict[str, Any]] = []

        for attachment in attachments:
            hydrated_attachment = dict(attachment)
            content_bytes: Optional[bytes] = None
            inline_data_b64 = attachment.get("inline_data_b64")
            attachment_id = attachment.get("attachment_id")

            if inline_data_b64:
                try:
                    content_bytes = self._urlsafe_b64_to_bytes(inline_data_b64)
                except Exception:
                    content_bytes = None
            elif attachment_id:
                content_bytes = await self.fetch_attachment_bytes(
                    account_id=account_id,
                    message_id=message_id,
                    attachment_id=attachment_id,
                )

            if content_bytes is None:
                hydrated.append(hydrated_attachment)
                continue

            if max_bytes is not None and len(content_bytes) > max_bytes:
                hydrated_attachment["content_skipped_reason"] = "max_bytes_exceeded"
                hydrated.append(hydrated_attachment)
                continue

            hydrated_attachment["data_b64"] = base64.b64encode(content_bytes).decode(
                "utf-8"
            )
            hydrated.append(hydrated_attachment)

        return hydrated

    async def fetch_all_emails(self) -> List[Dict[str, Any]]:
        """Fetch all unprocessed emails.

        Returns:
            List of standardized email objects
        """
        try:
            return await self.fetch_gmail_emails()
        except Exception as e:
            print(f"Error during email fetching: {str(e)}")
            return []
