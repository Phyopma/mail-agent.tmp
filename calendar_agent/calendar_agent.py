"""Calendar Agent Module for Mail Agent.

This module handles calendar event and reminder creation using Google Calendar API.
It provides functionality to create calendar events and reminders based on LLM tool calls.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
from email_fetcher.google_service_manager import GoogleServiceManager


class CalendarAgent:
    """Handles calendar operations using Google Calendar API."""

    def __init__(self):
        """Initialize the calendar agent."""
        self.service_manager = GoogleServiceManager()
        self.calendar_services = {}
        self.tasks_services = {}
        self.account_timezones = {}

    async def setup_calendar(self, credentials_path: str, token_path: str, account_id: str = 'default', timezone: str = 'UTC') -> None:
        services = await self.service_manager.setup_services(credentials_path, token_path, account_id)
        self.calendar_services[account_id] = services['calendar']
        self.tasks_services[account_id] = services['tasks']
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
        try:
            service = self.calendar_services.get(account_id)
            if not service:
                return {'status': 'error', 'error': f'Calendar service not found for account {account_id}'}

            # Get timezone for this account
            timezone = self.account_timezones.get(account_id, 'UTC')

            # Parse and convert timestamps to account timezone
            from datetime import datetime
            from zoneinfo import ZoneInfo

            # Convert start time
            start_time = datetime.fromisoformat(event_details['start'].replace('Z', '+00:00'))
            start_time = start_time.astimezone(ZoneInfo(timezone))

            # Convert end time (if provided)
            end_time = None
            if 'end' in event_details and event_details['end']:
                end_time = datetime.fromisoformat(event_details['end'].replace('Z', '+00:00'))
                end_time = end_time.astimezone(ZoneInfo(timezone))

            # Format event with timezone
            event = {
                'summary': event_details['summary'],
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': timezone
                },
                'end': {
                    'dateTime': (end_time or start_time).isoformat(),
                    'timeZone': timezone
                }
            }

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
