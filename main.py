#!/usr/bin/env python3

"""Mail Agent Main Module.

This module implements the main email processing pipeline that:
1. Fetches emails from multiple Gmail accounts
2. Preprocesses the emails for analysis
3. Analyzes them using LLM for spam detection, categorization, and required actions
4. Handles calendar events and reminders based on analysis
5. Tags and marks emails as processed
"""

import argparse
import asyncio
import json
from datetime import datetime, UTC
from typing import Dict, Any, List

from email_fetcher import EmailFetcher
from email_preprocessor import EmailPreprocessor
from spam_detector import UnifiedEmailAnalyzer
from email_tagger import EmailTagger
from calendar_agent import CalendarAgent


async def process_email_pipeline(email_data: Dict[str, Any],
                                 preprocessor: EmailPreprocessor,
                                 analyzer: UnifiedEmailAnalyzer,
                                 calendar_agent: CalendarAgent,
                                 tagger: EmailTagger,
                                 fetcher: EmailFetcher,
                                 label_ids: Dict[str, str]) -> Dict[str, Any]:
    """Process a single email through the complete pipeline.

    Args:
        email_data: Raw email data
        preprocessor: Email preprocessor instance
        analyzer: Email analyzer instance
        calendar_agent: Calendar agent instance
        tagger: Email tagger instance
        fetcher: Email fetcher instance
        label_ids: Dictionary of Gmail label IDs

    Returns:
        Dictionary containing processing results
    """
    try:
        print(f"\nProcessing email: {email_data['subject']}")
        print("-" * 60)

        # Preprocess email
        print("Preprocessing...")
        preprocessed = preprocessor.preprocess_email(email_data)

        if preprocessed['preprocessing_status'] == 'error':
            print(f"Preprocessing Error: {preprocessed['error_message']}")
            return None

        # Analyze email
        print("Analyzing...")
        analysis_result = await analyzer.analyze_email({
            'from': email_data['from'],
            'subject': email_data['subject'],
            'received_date': email_data['date'],
            'body': preprocessed['cleaned_body']
        })

        if not analysis_result:
            print("Analysis failed")
            return None

        # Handle calendar events and reminders
        if 'calendar' in analysis_result['required_tools']:
            print("Creating calendar event...")
            calendar_event = analysis_result['calendar_event']
            if calendar_event:
                event_details = {
                    'summary': calendar_event.title,
                    'start': calendar_event.start_time,
                    'end': calendar_event.end_time
                }
                if calendar_event.description:
                    event_details['description'] = calendar_event.description
                if calendar_event.attendees:
                    event_details['attendees'] = calendar_event.attendees

                result = await calendar_agent.create_event(event_details)
                if result['status'] == 'success':
                    print(
                        f"Calendar event created successfully: {result['html_link']}")
                else:
                    print(
                        f"Failed to create calendar event: {result['error']}")

        if 'reminder' in analysis_result['required_tools']:
            print("Creating reminder...")
            reminder = analysis_result['reminder']
            if reminder:
                event_details = {
                    'summary': reminder.title,
                    'start': reminder.due_date,
                    'reminder_type': 'reminder'
                }
                if reminder.priority:
                    event_details['priority'] = reminder.priority
                if reminder.description:
                    event_details['description'] = reminder.description

                result = await calendar_agent.create_event(event_details)
                if result['status'] == 'success':
                    print(
                        f"Reminder created successfully: {result['html_link']}")
                else:
                    print(f"Failed to create reminder: {result['error']}")

        # Apply tags based on analysis
        print("Applying tags...")
        tagged_email = tagger.tag_email(email_data, analysis_result)

        # Format complete result
        result = {
            'metadata': {
                'email_id': email_data['id'],
                'account_id': email_data['account_id'],
                'timestamp': datetime.now(UTC).isoformat()
            },
            'email': {
                'from': email_data['from'],
                'subject': email_data['subject'],
                'date': email_data['date']
            },
            'preprocessing': {
                'status': preprocessed['preprocessing_status'],
                'content_length': len(preprocessed['cleaned_body'])
            },
            'analysis': analysis_result,
            'tagging': tagged_email['tags']
        }

        # Convert tag names to label IDs and mark as processed
        tag_label_ids = [label_ids[tag] for tag in tagged_email['tags']
                         if tag in label_ids]

        processed_label_id = label_ids.get('ProcessedByAgent')
        if processed_label_id:
            service = fetcher.gmail_services[email_data['account_id']]
            await asyncio.to_thread(
                service.users().messages().modify(
                    userId='me',
                    id=email_data['id'],
                    body={'addLabelIds': [processed_label_id] + tag_label_ids}
                ).execute
            )
            print("Email marked as processed with tags")

        return result

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return None


async def run_pipeline(accounts_config: List[Dict[str, str]], analyzer_type: str = 'ollama'):
    """Run the complete email processing pipeline for multiple accounts.

    Args:
        accounts_config: List of account configurations with credentials and token paths
        analyzer_type: Type of analyzer to use ('ollama' or 'lmstudio')
    """
    try:
        print("\n=== Starting Email Processing Pipeline ===")
        print(f"Using {analyzer_type.capitalize()} for analysis\n")

        # Initialize components
        fetcher = EmailFetcher()
        preprocessor = EmailPreprocessor()
        analyzer = UnifiedEmailAnalyzer(
            backend=analyzer_type.lower(),
            max_concurrent_requests=3
        )
        calendar_agent = CalendarAgent()
        tagger = EmailTagger()

        # Setup Gmail clients for all accounts
        print("Setting up Gmail clients...")
        for account in accounts_config:
            account_id = account.get('id', 'default')
            await fetcher.setup_gmail(
                account['credentials_path'],
                account['token_path'],
                account_id
            )

            # Initialize calendar service with same credentials
            print(f"Setting up calendar service for {account_id}...")
            await calendar_agent.setup_calendar(
                account['credentials_path'],
                account['token_path'],
                account_id,
                account.get('timezone', 'UTC')
            )

        # Fetch unprocessed emails from all accounts
        print(
            f"\nFetching unprocessed emails from the last 24 hours...")
        all_emails = await fetcher.fetch_all_emails()

        if not all_emails:
            print("No unprocessed emails found.")
            return

        print(
            f"\nFound {len(all_emails)} unprocessed emails. Processing...\n")

        # Process emails from all accounts
        results = []
        for email in all_emails:
            # Get label IDs for the current account
            if email['account_id'] not in fetcher.label_ids:
                print(
                    f"Error: Label IDs not found for account {email['account_id']}")
                continue

            result = await process_email_pipeline(
                email,
                preprocessor,
                analyzer,
                calendar_agent,
                tagger,
                fetcher,
                fetcher.label_ids[email['account_id']]
            )

            if result:
                results.append(result)

        # Print summary
        print("\n=== Pipeline Summary ===")
        print(f"Total emails processed: {len(results)}")
        print(f"Successful: {len(results)}")
        print(f"Failed: {len(all_emails) - len(results)}")

    except Exception as e:
        print(f"Pipeline Error: {str(e)}")


def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Mail Agent Email Processing Pipeline')

    parser.add_argument(
        '--accounts',
        type=str,
        required=True,
        help='JSON file containing account configurations'
    )
    parser.add_argument(
        '--analyzer',
        type=str,
        choices=['ollama', 'lmstudio'],
        default='ollama',
        help='Type of analyzer to use (ollama or lmstudio)'
    )

    args = parser.parse_args()

    # Load accounts configuration
    try:
        with open(args.accounts) as f:
            config = json.load(f)
            accounts_config = config['accounts']
    except Exception as e:
        print(f"Error loading accounts configuration: {str(e)}")
        return

    # Run the pipeline
    asyncio.run(run_pipeline(accounts_config, analyzer_type=args.analyzer))


if __name__ == '__main__':
    main()
