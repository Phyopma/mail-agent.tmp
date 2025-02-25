#!/usr/bin/env python3

"""CLI tool for testing the Email Fetcher module.

This script provides a command-line interface to test the email fetcher functionality
by fetching emails from Gmail using provided credentials.
"""

import argparse
import asyncio
from email_fetcher import EmailFetcher

async def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Test Gmail email fetching functionality'
    )
    parser.add_argument(
        '--credentials',
        required=True,
        help='Path to Gmail API credentials JSON file'
    )
    parser.add_argument(
        '--token',
        required=True,
        help='Path to save/load Gmail token pickle file'
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize email fetcher
        fetcher = EmailFetcher()
        
        # Setup Gmail clients
        print("Setting up Gmail clients...")
        # Setup default account
        await fetcher.setup_gmail(args.credentials, args.token, 'default')
        
        # Example of setting up additional account (commented out)
        # await fetcher.setup_gmail(
        #     "path/to/work_credentials.json",
        #     "path/to/work_token.pickle",
        #     'work'
        # )
        
        # Fetch emails from all accounts
        print("\nFetching unprocessed emails from the last 24 hours...")
        emails = await fetcher.fetch_all_emails()
        
        # Display results
        if not emails:
            print("No unprocessed emails found.")
        else:
            print(f"\nFound {len(emails)} unprocessed emails:")
            for email in emails:
                print(f"\nAccount: {email['account_id']}")
                print(f"Subject: {email['subject']}")
                print(f"From: {email['from']}")
                print(f"Date: {email['date']}")
                print("-" * 50)
                
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())