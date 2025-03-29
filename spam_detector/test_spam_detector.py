"""Test script for the Email Analysis Module.

This script validates the email analysis functionality using sample emails.
"""

import asyncio
from spam_detector import UnifiedEmailAnalyzer

# Sample emails for testing
SAMPLE_EMAILS = [
    {
        'from': 'marketing@special-offers.com',
        'subject': 'CONGRATULATIONS! You\'ve WON $1,000,000!!!',
        'received_date': '2024-03-14T09:30:00Z',
        'body': 'Dear Lucky Winner!\n\nYou have been selected to receive $1,000,000! Click here NOW to claim your prize! Limited time offer!\n\nACT FAST!!!!\n\nBest regards,\nPrize Department'
    },
    {
        'from': 'colleague@company.com',
        'subject': 'Meeting notes from yesterday',
        'received_date': '2024-03-14T15:45:00Z',
        'body': 'Hi team,\n\nAttached are the meeting notes from yesterday\'s discussion about the Q2 planning.\n\nBest regards,\nJohn'
    },
    {
        'from': 'prince@foreign-country.com',
        'subject': 'Urgent Business Proposal - Confidential',
        'received_date': '2024-03-14T11:20:00Z',
        'body': 'Dear Sir/Madam,\n\nI am a prince from a wealthy family. I need your help to transfer $50 million. Please send your bank details and I will share 30% with you.\n\nUrgent reply needed!\n\nBest regards,\nPrince'
    },
    {
        'from': 'team-lead@company.com',
        'subject': 'Project Review Meeting - Tomorrow 10 AM',
        'received_date': '2024-03-14T16:00:00Z',
        'body': 'Dear Team,\n\nLet\'s meet tomorrow at 10 AM for the Q2 project review. Please prepare your status updates.\n\nMeeting Link: https://meet.company.com/q2-review\nDate: 2024-03-15\nTime: 10:00 AM - 11:30 AM\n\nRegards,\nSarah'
    },
    {
        'from': 'mom@family.com',
        'subject': 'Family Dinner This Weekend',
        'received_date': '2024-03-14T13:15:00Z',
        'body': 'Hi sweetie,\n\nDon\'t forget we\'re having family dinner this Saturday at 6 PM. Your sister is bringing her famous lasagna.\n\nLove you!\nMom'
    }
]


async def test_email_analysis():
    """Test the email analysis module with sample emails."""
    analyzer = UnifiedEmailAnalyzer()

    print("Testing Email Analysis...\n")

    for i, email in enumerate(SAMPLE_EMAILS, 1):
        print(f"\nTesting Email {i}:")
        print(f"From: {email['from']}")
        print(f"Subject: {email['subject']}")
        print("Body: ", email['body'][:100], "...")

        result = await analyzer.analyze_email(email)

        if result:
            print("\nResults:")
            print(f"Is Spam: {result['is_spam']}")
            print(f"Category: {result['category']}")
            print(f"Priority: {result['priority']}")
            print(f"Reasoning: {result['reasoning']}")

            # Display tool detection results
            print("\nRequired Tools:")
            if result['required_tools']:
                for tool in result['required_tools']:
                    print(f"- {tool}")
                    if tool == 'calendar' and result.get('calendar_event'):
                        calendar_event = result['calendar_event']
                        print("  Calendar Event Details:")
                        print(f"    Title: {calendar_event.title}")
                        print(f"    Start Time: {calendar_event.start_time}")
                        if calendar_event.end_time:
                            print(f"    End Time: {calendar_event.end_time}")
                        if calendar_event.description:
                            print(
                                f"    Description: {calendar_event.description}")
                        if calendar_event.attendees:
                            print(
                                f"    Attendees: {', '.join(calendar_event.attendees)}")
                    elif tool == 'reminder' and result.get('reminder'):
                        reminder = result['reminder']
                        print("  Reminder Details:")
                        print(f"    Title: {reminder.title}")
                        print(f"    Due Date: {reminder.due_date}")
                        print(f"    Priority: {reminder.priority}")
                        if reminder.description:
                            print(f"    Description: {reminder.description}")
            else:
                print("No tools required")
        else:
            print("\nError: Failed to analyze email")

        print("\n" + "-"*50)


async def test_batch_email_analysis():
    """Test the batch email analysis functionality."""
    analyzer = UnifiedEmailAnalyzer()

    print("\nTesting Batch Email Analysis...\n")
    print(f"Processing {len(SAMPLE_EMAILS)} emails concurrently...")

    import time
    start_time = time.time()

    # Process all emails in a batch
    results = await analyzer.analyze_email_batch(SAMPLE_EMAILS)

    end_time = time.time()
    elapsed_time = end_time - start_time

    print(f"\nBatch processing completed in {elapsed_time:.2f} seconds")
    print(
        f"Average time per email: {elapsed_time/len(SAMPLE_EMAILS):.2f} seconds")

    # Print summary of results
    print("\nBatch Results Summary:")
    for i, (email, result) in enumerate(zip(SAMPLE_EMAILS, results), 1):
        if result:
            print(
                f"{i}. {email['subject']} - {result['is_spam']} - {result['category']} - {result['priority']}")
        else:
            print(f"{i}. {email['subject']} - Analysis failed")

    print("\n" + "-"*50)


if __name__ == "__main__":
    # Run individual email analysis test
    # asyncio.run(test_email_analysis())

    # Run batch email analysis test
    asyncio.run(test_batch_email_analysis())
