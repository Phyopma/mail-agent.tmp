"""Google Service Manager Module for Mail Agent.

This module provides a unified interface for managing Google API services
including Gmail, Calendar, and Tasks.
"""

from typing import Dict, Any, Optional
import os
import pickle
import asyncio
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

class GoogleServiceManager:
    """Manages Google API service initialization and authentication."""

    # Define all required scopes
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events',
        'https://www.googleapis.com/auth/tasks'
    ]
    
    # Cloud Run secret mount path mappings
    # Maps local paths to Cloud Run secret mount paths
    CLOUD_RUN_PATH_MAP = {
        'credentials/gmail_credentials.json': '/app/secrets/gmail-creds/gmail_credentials.json',
        'credentials/gmail_token.pickle': '/app/secrets/gmail-token/gmail_token.pickle',
        'credentials/uci_token.pickle': '/app/secrets/uci-token/uci_token.pickle',
    }

    def __init__(self):
        self.services = {}
    
    def _resolve_path(self, path: str) -> str:
        """Resolve a credential path with fallbacks for Cloud Run.
        
        Checks paths in order:
        1. The path as-is (for local development)
        2. Cloud Run secret mount path mapping
        3. Absolute path variations
        
        Args:
            path: Original credential path from config
            
        Returns:
            Resolved path that exists, or original path if none found
        """
        # First, try the path as-is
        if os.path.exists(path):
            return path
        
        # Try Cloud Run secret mount path mapping
        if path in self.CLOUD_RUN_PATH_MAP:
            cloud_path = self.CLOUD_RUN_PATH_MAP[path]
            if os.path.exists(cloud_path):
                return cloud_path
        
        # Try with /app prefix (Cloud Run workdir)
        app_path = f"/app/{path}"
        if os.path.exists(app_path):
            return app_path
        
        # Check the Cloud Run path map for basename matches
        basename = os.path.basename(path)
        for local_path, cloud_path in self.CLOUD_RUN_PATH_MAP.items():
            if os.path.basename(cloud_path) == basename and os.path.exists(cloud_path):
                return cloud_path
        
        # Return original path (will fail with helpful error message)
        return path

    async def setup_services(self, credentials_path: str, token_path: str, account_id: str = 'default') -> Dict[str, Any]:
        """Setup Google API services for Gmail, Calendar, and Tasks.

        Args:
            credentials_path: Path to the Google API credentials file
            token_path: Path to save/load the token
            account_id: Unique identifier for this account

        Returns:
            Dictionary containing initialized service clients
        """
        try:
            # Resolve paths for Cloud Run environment
            resolved_credentials_path = self._resolve_path(credentials_path)
            resolved_token_path = self._resolve_path(token_path)
            
            # Get credentials
            creds = await self._get_credentials(resolved_credentials_path, resolved_token_path)

            # Initialize services
            if account_id not in self.services:
                self.services[account_id] = {}

            # Build Gmail service
            self.services[account_id]['gmail'] = build('gmail', 'v1', credentials=creds)

            # Build Calendar service
            self.services[account_id]['calendar'] = build('calendar', 'v3', credentials=creds)

            # Build Tasks service
            self.services[account_id]['tasks'] = build('tasks', 'v1', credentials=creds)

            return self.services[account_id]

        except Exception as e:
            raise Exception(f"Error setting up Google services: {str(e)}")

    async def _get_credentials(self, credentials_path: str, token_path: str) -> Credentials:
        """Get or refresh Google API credentials.

        Args:
            credentials_path: Path to the credentials JSON file
            token_path: Path to save/load the token

        Returns:
            Valid Google API credentials
        """
        creds = None

        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        return creds

    def get_service(self, account_id: str, service_type: str) -> Optional[Any]:
        """Get an initialized service client.

        Args:
            account_id: Account identifier
            service_type: Type of service ('gmail', 'calendar', or 'tasks')

        Returns:
            Initialized service client or None if not found
        """
        return self.services.get(account_id, {}).get(service_type)

    async def setup_gmail_labels(self, account_id: str) -> Dict[str, str]:
        """Create and manage Gmail labels for a specific account.

        Args:
            account_id: Identifier for the Gmail account

        Returns:
            Dictionary mapping label names to their IDs
        """
        service = self.get_service(account_id, 'gmail')
        if not service:
            raise ValueError(f"Gmail service not initialized for account {account_id}")

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
            label_ids = {}
            for label_name, label_config in required_labels.items():
                if label_name not in existing_label_names:
                    created_label = await asyncio.to_thread(
                        service.users().labels().create(
                            userId='me',
                            body=label_config
                        ).execute
                    )
                    label_ids[label_name] = created_label['id']
                    print(f"Created '{label_name}' label")
                else:
                    # Get ID of existing label
                    existing_label = next(
                        label for label in existing_labels.get('labels', [])
                        if label['name'] == label_name
                    )
                    label_ids[label_name] = existing_label['id']
                    print(f"'{label_name}' label already exists")

            print(f"Stored {len(label_ids)} label IDs for account {account_id}")
            return label_ids

        except Exception as e:
            print(f"Error setting up Gmail labels: {str(e)}")
            return {}