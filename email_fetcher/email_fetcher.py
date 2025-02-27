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


class EmailFetcher:
    """Handles fetching emails from Gmail."""

    def __init__(self):
        self.gmail_services = {}
        self.processed_tag = "ProcessedByAgent"
        self.label_ids = {}  # Store label IDs for each account

    async def setup_gmail(self, credentials_path: str, token_path: str, account_id: str = 'default') -> None:
        """Setup Gmail API client for a specific account.

        Args:
            credentials_path: Path to the Gmail API credentials file
            token_path: Path to save/load the Gmail token
            account_id: Unique identifier for this Gmail account
        """
        SCOPES = ['https://www.googleapis.com/auth/gmail.modify',
                  'https://www.googleapis.com/auth/calendar',
                  'https://www.googleapis.com/auth/calendar.events'
                  ]
        creds = None

        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        self.gmail_services[account_id] = build(
            'gmail', 'v1', credentials=creds)

        # Create required Gmail labels
        await self._setup_required_labels(account_id)

    async def _setup_required_labels(self, account_id: str) -> None:
        """Create required Gmail labels if they don't exist.

        Args:
            account_id: Identifier for the Gmail account
        """
        service = self.gmail_services[account_id]
        try:
            # Get existing labels
            existing_labels = await asyncio.to_thread(
                service.users().labels().list(userId='me').execute
            )
            existing_label_names = [label['name']
                                    for label in existing_labels.get('labels', [])]

            # Define required labels with their configurations
            required_labels = {
                'ProcessedByAgent': {
                    'name': 'ProcessedByAgent',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                # Priority labels
                'Priority/Critical': {
                    'name': 'Priority/Critical',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Priority/Urgent': {
                    'name': 'Priority/Urgent',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Priority/High': {
                    'name': 'Priority/High',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Priority/Normal': {
                    'name': 'Priority/Normal',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Priority/Low': {
                    'name': 'Priority/Low',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Priority/Ignore': {
                    'name': 'Priority/Ignore',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                # Category labels
                'Category/Work': {
                    'name': 'Category/Work',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/Personal': {
                    'name': 'Category/Personal',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/Family': {
                    'name': 'Category/Family',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/Social': {
                    'name': 'Category/Social',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/Marketing': {
                    'name': 'Category/Marketing',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/School': {
                    'name': 'Category/School',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/Newsletter': {
                    'name': 'Category/Newsletter',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                },
                'Category/Shopping': {
                    'name': 'Category/Shopping',
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                }
            }

            # Create missing labels and store all label IDs
            self.label_ids[account_id] = {}
            for label_name, label_config in required_labels.items():
                if label_name not in existing_label_names:
                    created_label = await asyncio.to_thread(
                        service.users().labels().create(
                            userId='me',
                            body=label_config
                        ).execute
                    )
                    self.label_ids[account_id][label_name] = created_label['id']
                    print(f"Created '{label_name}' label")
                else:
                    # Get ID of existing label
                    existing_label = next(
                        label for label in existing_labels.get('labels', [])
                        if label['name'] == label_name
                    )
                    self.label_ids[account_id][label_name] = existing_label['id']
                    print(f"'{label_name}' label already exists")

            print(
                f"Stored {len(self.label_ids[account_id])} label IDs for account {account_id}")

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
