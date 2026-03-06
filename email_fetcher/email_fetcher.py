"""Email Fetcher Module for Mail Agent.

This module handles fetching unprocessed emails from Gmail accounts.
It supports async operations and provides a standardized output format for LangGraph.
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import base64
from email.utils import parseaddr
from email_fetcher.google_service_manager import GoogleServiceManager


class EmailFetcher:
    """Handles fetching emails from Gmail."""

    def __init__(self):
        self.service_manager = GoogleServiceManager()
        self.processed_tag = "ProcessedByAgent"
        self.gmail_services = {}
        self.label_ids = {}
        self._sender_unread_stats_cache: Dict[Tuple[str, str, int, int], Dict[str, Any]] = {}

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

        for account_id, gmail_service in self.gmail_services.items():
            print(f"Fetching Gmail emails for account {account_id}...")
            # Query to filter emails:
            # - newer_than:1d - only emails from the last 24 hours
            # - -label:ProcessedByAgent - exclude emails already processed
            query = f"newer_than:1d -label:{self.processed_tag}"

            try:
                messages: List[Dict[str, Any]] = []
                next_page_token: Optional[str] = None
                while True:
                    list_call = gmail_service.users().messages().list(
                        userId='me',
                        q=query,
                        pageToken=next_page_token,
                    )
                    results = await asyncio.to_thread(list_call.execute)
                    messages.extend(results.get('messages', []))
                    next_page_token = results.get("nextPageToken")
                    if not next_page_token:
                        break

                for i, message in enumerate(messages):
                    if i > 0 and i % 5 == 0:
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
                    sender = self._get_header_value(headers, 'from')
                    body, attachments, has_non_text_content = self._extract_email_content(
                        payload
                    )
                    email_data = {
                        'id': msg['id'],
                        'provider': 'gmail',
                        'account_id': account_id,
                        'subject': self._get_header_value(headers, 'subject'),
                        'from': sender,
                        'sender_email': self._normalize_sender_email(sender),
                        'date': self._get_header_value(headers, 'date'),
                        'body': body,
                        'extraction_source': self._infer_body_extraction_source(payload, body),
                        'attachments': attachments,
                        'has_non_text_content': has_non_text_content,
                        'thread_id': msg['threadId']
                    }
                    all_emails.append(email_data)
            except Exception as e:
                print(
                    f"Error fetching Gmail emails for account {account_id}: {str(e)}")

        return all_emails

    def _normalize_sender_email(self, sender: str) -> str:
        """Extract and normalize sender email from a raw From header value."""
        parsed_name, parsed_email = parseaddr(sender or "")
        if parsed_email:
            return parsed_email.strip().lower()
        return (sender or "").strip().lower()

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

    def _infer_body_extraction_source(self, payload: Dict[str, Any], body: str) -> str:
        """Infer extraction source metadata based on available text parts."""
        if not body:
            return "none"

        parts = payload.get("parts", []) or []
        has_plain = bool(self._find_part_by_mime(parts, "text/plain"))
        has_html = bool(self._find_part_by_mime(parts, "text/html"))
        if has_plain and has_html:
            return "mixed"
        if has_plain:
            return "text_plain"
        if has_html:
            return "text_html"

        mime_type = str(payload.get("mimeType") or "").lower()
        if mime_type == "text/plain":
            return "text_plain"
        if mime_type == "text/html":
            return "text_html"
        return "text_plain"

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

    async def get_sender_unread_window_stats(
        self,
        account_id: str,
        sender_email: str,
        days: int,
        threshold: int,
    ) -> Dict[str, Any]:
        """Return unread volume stats for a sender in a recent time window.

        Reliability behavior is fail-open: API failures return a non-overload response.
        """
        normalized_sender = self._normalize_sender_email(sender_email)
        cache_key = (account_id, normalized_sender, int(days), int(threshold))
        cached = self._sender_unread_stats_cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        gmail_service = self.gmail_services.get(account_id)
        if not gmail_service or not normalized_sender:
            fallback = {
                "sender_unread_count_window": 0,
                "sender_overload": False,
            }
            self._sender_unread_stats_cache[cache_key] = dict(fallback)
            return fallback

        query = (
            f"from:{normalized_sender} newer_than:{int(days)}d "
            f"is:unread in:inbox -label:{self.processed_tag}"
        )
        count = 0
        next_page_token: Optional[str] = None

        try:
            while True:
                list_call = gmail_service.users().messages().list(
                    userId='me',
                    q=query,
                    pageToken=next_page_token,
                    maxResults=min(500, max(int(threshold), 1)),
                )
                result = await asyncio.to_thread(list_call.execute)
                batch = result.get("messages", [])
                count += len(batch)
                if count >= int(threshold):
                    break
                next_page_token = result.get("nextPageToken")
                if not next_page_token:
                    break
        except Exception as e:
            print(
                f"Warning: failed to fetch sender unread stats for {normalized_sender}: {str(e)}"
            )
            stats = {
                "sender_unread_count_window": 0,
                "sender_overload": False,
            }
            self._sender_unread_stats_cache[cache_key] = dict(stats)
            return stats

        stats = {
            "sender_unread_count_window": count,
            "sender_overload": count >= int(threshold),
        }
        self._sender_unread_stats_cache[cache_key] = dict(stats)
        return stats
