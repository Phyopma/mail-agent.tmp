"""Test script for the Spam Detection Module.

This script validates the spam detection functionality using sample emails.
"""

import asyncio
from spam_detector import SpamDetector

# Sample emails for testing
SAMPLE_EMAILS = [
    {
        'from': 'marketing@special-offers.com',
        'subject': 'CONGRATULATIONS! You\'ve WON $1,000,000!!!',
        'body': 'Dear Lucky Winner!\n\nYou have been selected to receive $1,000,000! Click here NOW to claim your prize! Limited time offer!\n\nACT FAST!!!!\n\nBest regards,\nPrize Department'
    },
    {
        'from': 'colleague@company.com',
        'subject': 'Meeting notes from yesterday',
        'body': 'Hi team,\n\nAttached are the meeting notes from yesterday\'s discussion about the Q2 planning.\n\nBest regards,\nJohn'
    },
    {
        'from': 'prince@foreign-country.com',
        'subject': 'Urgent Business Proposal - Confidential',
        'body': 'Dear Sir/Madam,\n\nI am a prince from a wealthy family. I need your help to transfer $50 million. Please send your bank details and I will share 30% with you.\n\nUrgent reply needed!\n\nBest regards,\nPrince'
    }
]


async def test_spam_detection():
    """Test the spam detection module with sample emails."""
    detector = SpamDetector()

    print("Testing Spam Detection...\n")

    for i, email in enumerate(SAMPLE_EMAILS, 1):
        print(f"\nTesting Email {i}:")
        print(f"From: {email['from']}")
        print(f"Subject: {email['subject']}")
        print("Body: ", email['body'][:100], "...")

        result = await detector.detect_spam(email)

        if result:
            print("\nResults:")
            print(f"Is Spam: {result['is_spam']}")
            print(f"Confidence: {result['confidence']:.2f}")
            print(f"Reasoning: {result['reasoning']}")
        else:
            print("\nError: Failed to analyze email")

        print("\n" + "-"*50)

if __name__ == "__main__":
    asyncio.run(test_spam_detection())
