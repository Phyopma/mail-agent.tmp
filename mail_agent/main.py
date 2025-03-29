#!/usr/bin/env python3
"""
Main entry point for the Mail Agent CLI.

This module provides the main functionality for the mail-agent command.
It implements the complete email processing pipeline that:
1. Fetches emails from multiple Gmail accounts
2. Preprocesses the emails for analysis
3. Analyzes them using LLM for spam detection, categorization, and required actions
4. Handles calendar events and reminders based on analysis
5. Tags and marks emails as processed
"""

import argparse
import asyncio
import json
import sys
import os
from datetime import datetime, UTC
from typing import Dict, Any, List
from dotenv import load_dotenv

# Import components
from email_fetcher import EmailFetcher
from email_preprocessor import EmailPreprocessor
from spam_detector import UnifiedEmailAnalyzer, ToolAction
from email_tagger import EmailTagger
from calendar_agent import CalendarAgent


async def process_email_pipeline(email_data: Dict[str, Any],
                                 preprocessor: EmailPreprocessor,
                                 analyzer: UnifiedEmailAnalyzer,
                                 calendar_agent: CalendarAgent,
                                 tagger: EmailTagger,
                                 fetcher: EmailFetcher,
                                 label_ids: Dict[str, str],
                                 timezone: str) -> Dict[str, Any]:
    """Process a single email through the complete pipeline.

    Args:
        email_data: Raw email data
        preprocessor: Email preprocessor instance
        analyzer: Email analyzer instance
        calendar_agent: Calendar agent instance
        tagger: Email tagger instance
        fetcher: Email fetcher instance
        label_ids: Dictionary of Gmail label IDs
        timezone: Timezone for calendar events

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

        # Create the analysis input data dictionary
        analysis_input = {
            'from': email_data['from'],
            'subject': email_data['subject'],
            'received_date': email_data['date'],
            'body': preprocessed['cleaned_body']
        }

        # Debug: Print the text being sent to LLM
        print("\n=== DEBUG: TEXT BEING SENT TO LLM ===")
        print(f"FROM: {analysis_input['from']}")
        print(f"SUBJECT: {analysis_input['subject']}")
        print(f"RECEIVED: {analysis_input['received_date']}")
        print("\nBODY (first 500 chars):")
        print(f"{analysis_input['body'][:500]}..." if len(
            analysis_input['body']) > 500 else analysis_input['body'])
        print("=" * 60 + "\n")

        # Send to LLM for analysis
        analysis_result = await analyzer.analyze_email(analysis_input, timezone)

        if not analysis_result:
            print("Analysis failed")
            return None

        # Also print the LLM's response for debugging
        print("\n=== DEBUG: LLM RESPONSE ===")
        print(f"PRIORITY: {analysis_result.get('priority')}")
        print(f"CATEGORY: {analysis_result.get('category')}")
        print(f"IS_SPAM: {analysis_result.get('is_spam')}")
        print(f"REQUIRED TOOLS: {analysis_result.get('required_tools')}")
        print(f"REASONING: {analysis_result.get('reasoning')[:300]}..." if analysis_result.get(
            'reasoning') and len(analysis_result.get('reasoning')) > 300 else analysis_result.get('reasoning'))
        print("=" * 60 + "\n")

        # Check if email is spam, if so, delete it and skip further processing
        if analysis_result.get('is_spam') == 'SPAM':
            print(f"Email detected as SPAM - Deleting and skipping further processing")

            try:
                # Get Gmail service for this account
                service = fetcher.gmail_services[email_data['account_id']]

                # Delete the email by moving it to trash
                await asyncio.to_thread(
                    service.users().messages().trash(
                        userId='me',
                        id=email_data['id']
                    ).execute
                )

                print(f"Email successfully moved to trash")

                # Return minimal result for logging purposes
                return {
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
                    'analysis': {
                        'is_spam': 'SPAM',
                        'action_taken': 'deleted'
                    }
                }
            except Exception as e:
                print(f"Error deleting spam email: {str(e)}")
                # Continue with processing if deletion fails
        else:
            print(f"Email categorized as NOT SPAM - Continuing with processing")

        # Check if email meets criteria for performing actions:
        # 1. Priority must be CRITICAL, URGENT, or HIGH
        # 2. Category must be WORK, PERSONAL, or SCHOOL
        priority = analysis_result.get('priority')
        category = analysis_result.get('category')

        # Define high priority levels and important categories
        high_priority_levels = ['CRITICAL', 'URGENT', 'HIGH']
        important_categories = ['WORK', 'PERSONAL', 'SCHOOL']

        should_perform_actions = (
            priority in high_priority_levels and
            category in important_categories
        )
        print(f"{priority} and {category} are determined by llm.")
        if not should_perform_actions:
            print(
                f"Skipping actions: {priority} and {category} don't meet criteria for actions")
        else:
            print(
                f"Performing actions for {priority} priority {category} email")
            # Handle calendar events, reminders, and tasks based on required_tools
            for tool in analysis_result['required_tools']:
                if tool == ToolAction.CALENDAR:
                    print("Creating calendar event...")
                    calendar_event = analysis_result.get('calendar_event')
                    if calendar_event:
                        event_details = {
                            'summary': calendar_event.title,
                            'start': calendar_event.start_time,
                            'end': calendar_event.end_time if calendar_event.end_time else None,
                            'description': calendar_event.description if hasattr(calendar_event, 'description') else None,
                            'location': calendar_event.location if hasattr(calendar_event, 'location') else None,
                            'attendees': calendar_event.attendees if hasattr(calendar_event, 'attendees') else None
                        }
                        result = await calendar_agent.create_event(event_details, email_data['account_id'])
                        if result['status'] == 'success':
                            print(
                                f"Calendar event created successfully: {result['html_link']}")
                        else:
                            print(
                                f"Failed to create calendar event: {result['error']}")

                elif tool == ToolAction.REMINDER:
                    print("Creating reminder...")
                    reminder = analysis_result.get('reminder')
                    if reminder:
                        result = await calendar_agent.create_reminder(
                            title=reminder.title,
                            due_date=reminder.due_date,
                            priority=reminder.priority if hasattr(
                                reminder, 'priority') else None,
                            description=reminder.description if hasattr(
                                reminder, 'description') else None,
                            account_id=email_data['account_id']
                        )
                        if result['status'] == 'success':
                            print(
                                f"Reminder created successfully: {result['html_link']}")
                        else:
                            print(
                                f"Failed to create reminder: {result['error']}")

                elif tool == ToolAction.TASK:
                    print("Creating task...")
                    task = analysis_result.get('task')
                    if task:
                        task_details = {
                            'title': task.title,
                            'description': task.description if hasattr(task, 'description') else None,
                            'due_date': task.due_date if hasattr(task, 'due_date') else None,
                            'priority': task.priority if hasattr(task, 'priority') else None,
                            'assignees': task.assignees if hasattr(task, 'assignees') else None
                        }
                        result = await calendar_agent.create_task(task_details, email_data['account_id'])
                        if result['status'] == 'success':
                            print(
                                f"Task created successfully: {result['self_link']}")
                        else:
                            print(f"Failed to create task: {result['error']}")

        # Apply tags based on analysis
        print("Applying tags...")
        tagged_email = await tagger.tag_email(email_data, analysis_result)

        # Convert analysis result to JSON serializable format
        serializable_analysis = {}
        for key, value in analysis_result.items():
            if hasattr(value, 'model_dump'):
                serializable_analysis[key] = value.model_dump()
            else:
                serializable_analysis[key] = value

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
            'analysis': serializable_analysis,
            'tagging': tagged_email['tags']
        }

        print("Processing complete", json.dumps(result, indent=4))

        # Convert tag names to label IDs and mark as processed
        # Debug: Print tags and available label IDs to diagnose the issue
        print(f"Email tags: {tagged_email['tags']}")
        print(f"Available label IDs keys: {list(label_ids.keys())}")

        # Normalize label keys for more robust matching
        normalized_label_ids = {}
        for key, value in label_ids.items():
            # Create a normalized version of each key (lowercase with no spaces)
            normalized_key = key.lower().replace(' ', '')
            normalized_label_ids[normalized_key] = value
            # Keep the original key as well
            normalized_label_ids[key] = value

        # Now try matching tags with both original and normalized label keys
        tag_label_ids = []
        for tag in tagged_email['tags']:
            # Try exact match first
            if tag in label_ids:
                tag_label_ids.append(label_ids[tag])
                print(f"Found exact match for tag: {tag}")
            # Try normalized match (remove spaces and lowercase)
            elif tag.lower().replace(' ', '') in normalized_label_ids:
                tag_label_ids.append(
                    normalized_label_ids[tag.lower().replace(' ', '')])
                print(f"Found normalized match for tag: {tag}")
            else:
                print(f"No match found for tag: {tag}")

        # Remove duplicates from tag_label_ids while preserving order
        tag_label_ids = list(dict.fromkeys(tag_label_ids))

        processed_label_id = label_ids.get('ProcessedByAgent')
        if processed_label_id:
            service = fetcher.gmail_services[email_data['account_id']]
            try:
                # More detailed logging before applying labels
                print(
                    f"Applying {len(tag_label_ids)} label IDs: {tag_label_ids}")

                # Actually apply the labels
                await asyncio.to_thread(
                    service.users().messages().modify(
                        userId='me',
                        id=email_data['id'],
                        body={'addLabelIds': [
                            processed_label_id] + tag_label_ids}
                    ).execute
                )
                print("Email successfully marked as processed with tags")
            except Exception as e:
                print(f"Error applying labels to email: {str(e)}")
        else:
            print("Warning: ProcessedByAgent label ID not found")

        return result

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return None


async def process_batch(email_batch: List[Dict[str, Any]],
                        preprocessor: EmailPreprocessor,
                        analyzer: UnifiedEmailAnalyzer,
                        calendar_agent: CalendarAgent,
                        tagger: EmailTagger,
                        fetcher: EmailFetcher,
                        label_ids: Dict[str, str],
                        timezone: str) -> List[Dict[str, Any]]:
    """Process a batch of emails through the preprocessing and analysis phases concurrently.

    Args:
        email_batch: List of raw email data
        preprocessor: Email preprocessor instance
        analyzer: Email analyzer instance
        calendar_agent: Calendar agent instance
        tagger: Email tagger instance
        fetcher: Email fetcher instance
        label_ids: Dictionary of Gmail label IDs
        timezone: Timezone for calendar events

    Returns:
        List of processing results
    """
    # Step 1: Preprocess all emails in the batch
    print(f"Preprocessing batch of {len(email_batch)} emails...")
    preprocessed_batch = []
    original_emails = []  # Keep track of original emails for tagging

    for email_data in email_batch:
        try:
            print(f"Preprocessing: {email_data.get('subject', 'No subject')}")
            preprocessed = preprocessor.preprocess_email(email_data)
            if preprocessed['preprocessing_status'] == 'error':
                print(
                    f"Error preprocessing email: {preprocessed.get('error', 'Unknown error')}")
                continue
            preprocessed_batch.append(preprocessed)
            # Store original email for later use
            original_emails.append(email_data)
        except Exception as e:
            print(f"Exception during preprocessing: {str(e)}")

    # Step 2: Analyze all preprocessed emails in batch
    if not preprocessed_batch:
        print("No emails to analyze after preprocessing")
        return []

    print(f"Analyzing batch of {len(preprocessed_batch)} emails...")
    analysis_results = await analyzer.analyze_email_batch(preprocessed_batch)

    # Step 3: Tag emails in batch
    print(f"Tagging batch of {len(original_emails)} emails...")
    try:
        tagged_emails = await tagger.tag_email_batch(original_emails, analysis_results)
    except Exception as e:
        print(f"Error during batch tagging: {str(e)}")
        # Fall back to individual tagging if batch tagging fails
        tagged_emails = []
        for email, analysis in zip(original_emails, analysis_results):
            try:
                tagged_email = await tagger.tag_email(email, analysis)
                tagged_emails.append(tagged_email)
            except Exception as tag_e:
                print(f"Error tagging email: {str(tag_e)}")
                # Add untagged email to maintain index alignment
                email['tagging_status'] = 'error'
                email['error_message'] = str(tag_e)
                tagged_emails.append(email)

    # Step 4: Process the rest of the pipeline for each email
    results = []
    for i, (preprocessed, analysis, tagged_email) in enumerate(zip(preprocessed_batch, analysis_results, tagged_emails)):
        if not analysis:
            print(
                f"Error analyzing email: {preprocessed.get('subject', 'No subject')}")
            continue

        print(
            f"Processing analyzed email: {preprocessed.get('subject', 'No subject')}")
        print(
            f"Analysis: Spam={analysis['is_spam']}, Category={analysis['category']}, Priority={analysis['priority']}")

        result = {
            'email_id': preprocessed.get('id'),
            'gmail_thread_id': preprocessed.get('thread_id'),
            'subject': preprocessed.get('subject'),
            'is_spam': analysis['is_spam'],
            'category': analysis['category'],
            'priority': analysis['priority'],
            'required_tools': analysis['required_tools'],
            'calendar_event': analysis.get('calendar_event'),
            'reminder': analysis.get('reminder'),
            'task': analysis.get('task'),
            'reasoning': analysis.get('reasoning'),
            'tagging_status': tagged_email.get('tagging_status', 'unknown'),
            'tags': tagged_email.get('tags', [])
        }

        # Process calendar events if needed
        if 'calendar' in analysis['required_tools'] and analysis.get('calendar_event'):
            try:
                print("Creating calendar event...")
                calendar_result = await calendar_agent.create_event(analysis['calendar_event'])
                result['calendar_result'] = calendar_result
            except Exception as e:
                print(f"Error creating calendar event: {str(e)}")
                result['calendar_result'] = {
                    'status': 'error', 'error': str(e)}

        # Mark email as processed in Gmail
        try:
            print("Tagging email...")
            tagger_result = await tagger.tag_email(
                email_id=preprocessed['id'],
                is_spam=analysis['is_spam'],
                category=analysis['category'],
                priority=analysis['priority']
            )
            result['tagging_result'] = tagger_result
        except Exception as e:
            print(f"Error tagging email: {str(e)}")
            result['tagging_result'] = {'status': 'error', 'error': str(e)}

        results.append(result)

    return results


async def run_pipeline(accounts_config: List[Dict[str, str]], analyzer_type: str = 'ollama',
                       timezone: str = 'America/Los_Angeles', batch_size: int = None):
    """Run the complete email processing pipeline for multiple accounts.

    Args:
        accounts_config: List of account configurations with credentials and token paths
        analyzer_type: Type of analyzer to use ('ollama' or 'lmstudio')
        timezone: Timezone for calendar events
        batch_size: Number of emails to process in a batch. If None, process one by one.
    """
    try:
        print("\n=== Starting Email Processing Pipeline ===")
        print(f"Using {analyzer_type.capitalize()} for analysis")
        if batch_size:
            print(f"Using batch processing with batch size of {batch_size}")
        else:
            print("Processing emails one by one")
        print()

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
            account_id = account.get('account_id', 'default')
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
                account.get('timezone', timezone)
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

        # Determine processing method based on batch_size
        if (batch_size):
            # Process emails in batches of the specified size
            for i in range(0, len(all_emails), batch_size):
                batch = all_emails[i:i+batch_size]
                print(
                    f"\nProcessing batch {i//batch_size + 1} ({len(batch)} emails)")
                print("-" * 60)

                # Use the existing process_batch function for batch processing
                batch_results = await process_batch(
                    email_batch=batch,
                    preprocessor=preprocessor,
                    analyzer=analyzer,
                    calendar_agent=calendar_agent,
                    tagger=tagger,
                    fetcher=fetcher,
                    label_ids=fetcher.label_ids,
                    timezone=timezone
                )

                results.extend(batch_results)
        else:
            # Process emails one by one
            for i, email in enumerate(all_emails):
                print(f"\nProcessing email {i+1} of {len(all_emails)}")
                print("-" * 60)

                result = await process_email_pipeline(
                    email_data=email,
                    preprocessor=preprocessor,
                    analyzer=analyzer,
                    calendar_agent=calendar_agent,
                    tagger=tagger,
                    fetcher=fetcher,
                    label_ids=fetcher.label_ids[email['account_id']],
                    timezone=timezone
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


async def process_emails(accounts_file: str, analyzer_type: str = 'ollama',
                         timezone: str = 'America/Los_Angeles', batch_size: int = None):
    """Process emails using the pipeline.

    Args:
        accounts_file: Path to JSON file containing account configurations
        analyzer_type: Type of analyzer to use ('ollama' or 'lmstudio')
        timezone: Timezone for calendar events
        batch_size: Number of emails to process in a batch. If None, process one by one.
    """
    try:
        # Get project root directory
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))

        # Load accounts configuration
        with open(accounts_file) as f:
            config = json.load(f)
            accounts_config = config['accounts']

        # Resolve relative paths for credentials
        for account in accounts_config:
            account['credentials_path'] = os.path.join(
                project_root, account['credentials_path'])
            account['token_path'] = os.path.join(
                project_root, account['token_path'])

        # Run the pipeline
        await run_pipeline(accounts_config, analyzer_type=analyzer_type, timezone=timezone, batch_size=batch_size)

    except Exception as e:
        print(f"Error loading accounts configuration: {str(e)}")


def main():
    """Main entry point for the mail-agent command."""
    # Load environment variables
    load_dotenv()

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Mail Agent CLI')
    parser.add_argument('--version', action='store_true',
                        help='Show version information')
    # parser.add_argument('--setup', action='store_true', help='Setup mail agent credentials')
    # parser.add_argument('--fetch', action='store_true', help='Fetch new emails')
    parser.add_argument('--process', action='store_true',
                        help='Process fetched emails')
    parser.add_argument(
        '--accounts',
        type=str,
        help='JSON file containing account configurations'
    )
    parser.add_argument(
        '--analyzer',
        type=str,
        choices=['ollama', 'lmstudio', 'openrouter'],
        default='openrouter',
        help='Type of analyzer to use (ollama or lmstudio or openrouter)'
    )
    parser.add_argument(
        '--timezone',
        type=str,
        default='America/Los_Angeles',
        help='Timezone for calendar events'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=None,
        help='Number of emails to process in a batch. If specified, batch processing will be used.'
    )

    args = parser.parse_args()

    # Handle version request
    if args.version:
        from mail_agent import __version__
        print(f"Mail Agent version {__version__}")
        return 0

    # Handle setup request
    # if args.setup:
    #     print("Setting up Mail Agent...")
    #     # Add setup code here
    #     return 0

    # # Handle fetch request
    # if args.fetch:
    #     print("Fetching new emails...")
    #     # Add fetch code here
    #     return 0

    # Handle process request
    if args.process:
        if not args.accounts:
            print("Error: --accounts parameter is required for processing emails")
            return 1

        print("Processing emails...")
        asyncio.run(process_emails(args.accounts,
                    args.analyzer, args.timezone, args.batch_size))
        return 0

    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
