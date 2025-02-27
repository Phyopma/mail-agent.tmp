"""Calendar Agent Module for Mail Agent.

This module handles calendar event and reminder creation using Google Calendar API.
It provides functionality to create calendar events and reminders based on LLM tool calls.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os


class CalendarAgent:
    """Handles calendar operations using Google Calendar API."""

    def __init__(self):
        """Initialize the calendar agent."""
        self.calendar_services = {}
        self.tasks_services = {}
        self.account_timezones = {}

    async def setup_calendar(self, credentials_path: str, token_path: str, account_id: str = 'default', timezone: str = 'UTC') -> None:
        """Setup Google Calendar API client for a specific account.

        Args:
            credentials_path: Path to the Google API credentials file
            token_path: Path to save/load the Google token
            account_id: Unique identifier for this Google account
            timezone: Timezone for this account's calendar operations
        """
        SCOPES = ['https://www.googleapis.com/auth/gmail.modify',
                  'https://www.googleapis.com/auth/calendar',
                  'https://www.googleapis.com/auth/calendar.events',
                  'https://www.googleapis.com/auth/tasks'
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

        self.calendar_services[account_id] = build('calendar', 'v3', credentials=creds)
        self.tasks_services[account_id] = build('tasks', 'v1', credentials=creds)
        # Store timezone for this account
        self.account_timezones[account_id] = timezone

    async def create_task(self, task_details: Dict[str, Any], account_id: str = 'default') -> Dict[str, Any]:
        """Create a task using Google Tasks API.

        Args:
            task_details: Dictionary containing task details
            account_id: Identifier for the Google account

        Returns:
            Dictionary containing the created task details or error information
        """
        try:
            service = self.tasks_services.get(account_id)
            if not service:
                return {'status': 'error', 'error': f'Tasks service not found for account {account_id}'}

            # Get the default task list
            tasklist = await asyncio.to_thread(
                service.tasklists().list().execute
            )
            tasklist_id = tasklist['items'][0]['id']

            # Prepare task data
            task = {
                'title': task_details['title'],
                'notes': task_details.get('description', '')
            }

            if task_details.get('due_date'):
                task['due'] = task_details['due_date']

            # Create the task
            result = await asyncio.to_thread(
                service.tasks().insert(
                    tasklist=tasklist_id,
                    body=task
                ).execute
            )

            return {
                'status': 'success',
                'task_id': result['id'],
                'self_link': result['selfLink']
            }

        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    async def create_reminder(self, title: str, due_date: str, priority: Optional[str] = None, description: Optional[str] = None, account_id: str = 'default') -> Dict[str, Any]:
        """Create a reminder using Google Calendar API.

        Args:
            title: Title of the reminder
            due_date: Due date in ISO format
            priority: Priority level (high, medium, low)
            description: Optional description for the reminder
            account_id: Identifier for the Google account

        Returns:
            Dictionary containing the created reminder details or error information
        """
        event_details = {
            'summary': title,
            'start': due_date,
            'reminder_type': 'reminder'
        }

        if priority:
            event_details['priority'] = priority
        if description:
            event_details['description'] = description

        return await self.create_event(event_details, account_id)

    async def create_event(self, event_details: Dict[str, Any], account_id: str = 'default') -> Dict[str, Any]:
        """Create a calendar event or reminder.

        Args:
            event_details: Dictionary containing event details
            account_id: Account identifier for calendar service

        Returns:
            Dictionary containing operation status and event link
        """
        try:
            service = self.calendar_services.get(account_id)
            if not service:
                return {'status': 'error', 'error': f'Calendar service not found for account {account_id}'}

            # Get timezone for this account
            timezone = self.account_timezones.get(account_id, 'UTC')

            # Format event with timezone
            event = {
                'summary': event_details['summary'],
                'start': {
                    'dateTime': event_details['start'],
                    'timeZone': timezone
                },
                'end': {
                    'dateTime': event_details.get('end', event_details['start']),
                    'timeZone': timezone
                }
            }

            # For regular calendar events, add end time
            if not is_reminder:
                event['end'] = {
                    'dateTime': event_details['end'], 'timeZone': 'UTC'}
            else:
                # For reminders, set end time to start time and add reminder properties
                event['end'] = {
                    'dateTime': event_details['start'], 'timeZone': 'UTC'}
                event['reminders'] = {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 0}
                    ]
                }
                if 'priority' in event_details:
                    event['description'] = f"Priority: {event_details['priority']}\n" + \
                        event_details.get('description', '')

            # Add optional fields if provided
            if 'description' in event_details:
                event['description'] = event_details['description']
            if 'location' in event_details:
                event['location'] = event_details['location']
            if 'attendees' in event_details:
                # Validate email addresses before adding
                valid_attendees = []
                for email in event_details['attendees']:
                    # Basic email validation
                    if '@' in email and '.' in email.split('@')[1]:
                        valid_attendees.append({'email': email})
                if valid_attendees:
                    event['attendees'] = valid_attendees

            # Create the event
            calendar_service = self.calendar_services[account_id]
            created_event = await asyncio.to_thread(
                calendar_service.events().insert(
                    calendarId='primary',
                    body=event,
                    sendUpdates='all'
                ).execute
            )

            return {
                'status': 'success',
                'event_id': created_event['id'],
                'html_link': created_event['htmlLink']
            }

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
