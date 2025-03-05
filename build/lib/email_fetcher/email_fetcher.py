"""Email Fetcher Module for Mail Agent.

This module handles fetching unprocessed emails from Gmail accounts.
It supports async operations and provides a standardized output format for LangGraph.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os
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
                    all_emails.append(email_data)
            except Exception as e:
                print(
                    f"Error fetching Gmail emails for account {account_id}: {str(e)}")

        return all_emails

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
        """Fetch all unprocessed emails.

        Returns:
            List of standardized email objects
        """
        try:
            return await self.fetch_gmail_emails()
        except Exception as e:
            print(f"Error during email fetching: {str(e)}")
            return []