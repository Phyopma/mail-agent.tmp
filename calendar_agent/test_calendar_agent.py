
"""Test script for Calendar Agent functionality.

This script provides comprehensive tests for the calendar agent,
including both calendar events and reminders creation.
"""

import argparse
import asyncio
from datetime import datetime, timedelta
from calendar_agent import CalendarAgent


async def test_calendar_event():
    """Test creating a regular calendar event."""
    now = datetime.utcnow()

    event_details = {
        'summary': 'Team Meeting',
        'description': 'Weekly team sync meeting',
        'start': (now + timedelta(hours=1)).isoformat() + 'Z',
        'end': (now + timedelta(hours=2)).isoformat() + 'Z',
        'location': 'Virtual Meeting Room',
        'attendees': ['team@example.com']
    }

    return event_details


async def test_reminder():
    """Test creating a reminder."""
    now = datetime.utcnow()

    reminder_details = {
        'summary': 'Project Deadline',
        'description': 'Submit project documentation',
        'start': (now + timedelta(days=1)).isoformat() + 'Z',
        'reminder_type': 'reminder',
        'priority': 'high'
    }

    return reminder_details


async def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Test Google Calendar event and reminder creation'
    )
    parser.add_argument(
        '--credentials',
        type=str,
        default='credentials/gmail_credentials.json',
        help='Path to Google Calendar API credentials file'
    )
    parser.add_argument(
        '--token',
        type=str,
        default='credentials/gmail_token.pickle',
        help='Path to Google Calendar token file'
    )

    args = parser.parse_args()

    try:
        # Initialize calendar agent
        agent = CalendarAgent()
        print("\nSetting up Calendar client...")
        await agent.setup_calendar(args.credentials, args.token)

        # Test calendar event creation
        print("\nTesting calendar event creation...")
        event_details = await test_calendar_event()
        event_result = await agent.create_event(event_details)

        if event_result['status'] == 'success':
            print("Calendar event created successfully:")
            print(f"Event ID: {event_result['event_id']}")
            print(f"Event Link: {event_result['html_link']}")
        else:
            print(f"Error creating calendar event: {event_result['error']}")

        # Test reminder creation
        print("\nTesting reminder creation...")
        reminder_details = await test_reminder()
        reminder_result = await agent.create_event(reminder_details)

        if reminder_result['status'] == 'success':
            print("Reminder created successfully:")
            print(f"Reminder ID: {reminder_result['event_id']}")
            print(f"Reminder Link: {reminder_result['html_link']}")
        else:
            print(f"Error creating reminder: {reminder_result['error']}")

    except Exception as e:
        print(f"\nError: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())
