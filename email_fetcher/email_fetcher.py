"""Email Fetcher Module for Mail Agent.

This module handles fetching unprocessed emails from Gmail accounts.
It supports async operations and provides a standardized output format for LangGraph.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from .google_service_manager import GoogleServiceManager


class EmailFetcher:
    """Handles fetching emails from Gmail."""

    def __init__(self):
        self.service_manager = GoogleServiceManager()
        self.processed_tag = "ProcessedByAgent"
        self.label_ids = {}  # Store label IDs for each account
        self.gmail_services = {}  # Keep this for backward compatibility

    async def setup_gmail(self, credentials_path: str, token_path: str, account_id: str = 'default') -> None:
        """Setup Gmail API client for a specific account.

        Args:
            credentials_path: Path to the Gmail API credentials file
            token_path: Path to save/load the Gmail token
            account_id: Unique identifier for this Gmail account
        """
        services = await self.service_manager.setup_services(credentials_path, token_path, account_id)
        self.gmail_services[account_id] = services['gmail']

        # Create required Gmail labels
        await self._setup_required_labels(account_id)

    async def _setup_required_labels(self, account_id: str) -> None:
        """Create required Gmail labels if they don't exist.

        Args:
            account_id: Identifier for the Gmail account
        """
        try:
            # Use the service manager to setup labels
            self.label_ids[account_id] = await self.service_manager.setup_gmail_labels(account_id)
        except Exception as e:
            print(f"Error setting up Gmail labels: {str(e)}")

    async def fetch_gmail_emails(self, account_id: str = 'default') -> List[Dict[str, Any]]:
        """Fetch unprocessed emails from a specific Gmail account within the last 24 hours.

        Args:
            account_id: Identifier for the Gmail account to fetch from

        Returns:
            List of standardized email objects
        """
        if account_id not in self.gmail_services:
            raise ValueError(
                f"Gmail service for account {account_id} not initialized. Call setup_gmail() first.")

        gmail_service = self.gmail_services[account_id]
        yesterday = (datetime.utcnow() - timedelta(days=1)
                     ).strftime('%Y/%m/%d')
        query = f"after:{yesterday} -label:{self.processed_tag}"

        try:
            results = await asyncio.to_thread(
                gmail_service.users().messages().list(userId='me', q=query).execute
            )

            messages = results.get('messages', [])
            emails = []

            for message in messages:
                msg = await asyncio.to_thread(
                    gmail_service.users().messages().get(
                        userId='me', id=message['id'], format='full'
                    ).execute
                )

                headers = msg['payload']['headers']
                email_data = {
                    'id': msg['id'],
                    'provider': 'gmail',
                    'account_id': account_id,
                    'subject': next(h['value'] for h in headers if h['name'].lower() == 'subject'),
                    'from': next(h['value'] for h in headers if h['name'].lower() == 'from'),
                    'date': next(h['value'] for h in headers if h['name'].lower() == 'date'),
                    'body': self._get_email_body(msg['payload']),
                    'thread_id': msg['threadId']
                }
                emails.append(email_data)

            return emails

        except Exception as e:
            print(
                f"Error fetching Gmail emails for account {account_id}: {str(e)}")
            return []

    def _get_email_body(self, payload: Dict[str, Any]) -> str:
        """Extract email body from Gmail message payload.

        Args:
            payload: Gmail message payload

        Returns:
            Extracted email body text
        """
        if 'body' in payload and payload['body'].get('data'):
            return payload['body']['data']

        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and part['body'].get('data'):
                    return part['body']['data']

        return ""

    async def fetch_all_emails(self) -> List[Dict[str, Any]]:
        """Fetch all unprocessed emails from all configured accounts.

        Returns:
            List of standardized email objects from all accounts
        """
        all_emails = []
        try:
            for account_id in self.gmail_services:
                emails = await self.fetch_gmail_emails(account_id)
                all_emails.extend(emails)
            return all_emails
        except Exception as e:
            print(f"Error during email fetching: {str(e)}")
            return []
