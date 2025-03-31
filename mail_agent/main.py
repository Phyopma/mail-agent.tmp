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
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Import components
from email_fetcher import EmailFetcher
from email_preprocessor import EmailPreprocessor
from spam_detector import UnifiedEmailAnalyzer, ToolAction
from email_tagger import EmailTagger
from calendar_agent import CalendarAgent

from .config import config
from .logger import get_logger

# Initialize logger
logger = get_logger(__name__)


async def process_email_pipeline(email_data: Dict[str, Any],
                                 preprocessor: EmailPreprocessor,
                                 analyzer: UnifiedEmailAnalyzer,
                                 calendar_agent: CalendarAgent,
                                 tagger: EmailTagger,
                                 fetcher: EmailFetcher,
                                 label_ids: Dict[str, str],
                                 timezone: str) -> Optional[Dict[str, Any]]:
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
        logger.info(f"Processing email: {email_data.get('id', 'Unknown ID')}")
        logger.info(f"Subject: {email_data.get('subject', 'No subject')}")

        # Preprocess email
        logger.info("Preprocessing email...")
        preprocessed = preprocessor.preprocess_email(email_data)

        if preprocessed['preprocessing_status'] == 'error':
            logger.error(
                f"Preprocessing error: {preprocessed.get('error_message', 'Unknown error')}")
            return None

        # Prepare analysis input
        analysis_input = {
            'from': email_data['from'],
            'subject': email_data['subject'],
            'body': preprocessed['cleaned_body'],
            'received_date': email_data['date']
        }

        # Log preprocessing results
        logger.info(f"FROM: {analysis_input['from']}")
        logger.info(f"SUBJECT: {analysis_input['subject']}")
        logger.info(f"RECEIVED: {analysis_input['received_date']}")
        logger.debug(
            f"BODY (first 500 chars): {analysis_input['body'][:500]}...")

        # Send to LLM for analysis
        logger.info("Analyzing email...")
        analysis_result = await analyzer.analyze_email(analysis_input, timezone)

        if not analysis_result:
            logger.error("Analysis failed")
            return None

        # Log analysis results
        logger.info(f"PRIORITY: {analysis_result.get('priority')}")
        logger.info(f"CATEGORY: {analysis_result.get('category')}")
        logger.info(f"IS_SPAM: {analysis_result.get('is_spam')}")
        logger.debug(
            f"REQUIRED TOOLS: {analysis_result.get('required_tools', [])}")

        # Only take actions for important emails
        priority = analysis_result.get('priority', '').upper()
        category = analysis_result.get('category', '').upper()
        high_priority_levels = ['URGENT', 'HIGH']
        important_categories = ['WORK', 'PERSONAL', 'SCHOOL']

        should_perform_actions = (
            priority in high_priority_levels and
            category in important_categories
        )

        logger.info(f"{priority} and {category} determined by LLM")

        if not should_perform_actions:
            logger.info(
                f"Skipping actions: {priority} and {category} don't meet criteria for actions")
        else:
            logger.info(
                f"Performing actions for {priority} priority {category} email")

            # Handle calendar events, reminders, and tasks based on required_tools
            for tool in analysis_result['required_tools']:
                if tool == 'calendar':
                    logger.info("Creating calendar event...")
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
                            logger.info(
                                f"Calendar event created successfully: {result['html_link']}")
                        else:
                            logger.error(
                                f"Failed to create calendar event: {result['error']}")

                elif tool == 'reminder':
                    logger.info("Creating reminder...")
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
                            logger.info(
                                f"Reminder created successfully: {result['html_link']}")
                        else:
                            logger.error(
                                f"Failed to create reminder: {result['error']}")

                elif tool == 'task':
                    logger.info("Creating task...")
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
                            logger.info(
                                f"Task created successfully: {result['self_link']}")
                        else:
                            logger.error(
                                f"Failed to create task: {result['error']}")

        # Apply tags based on analysis
        logger.info("Applying tags...")
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

        logger.info("Processing complete")
        logger.debug(f"Result: {json.dumps(result, indent=4)}")

        # Convert tag names to label IDs and mark as processed
        logger.debug(f"Email tags: {tagged_email['tags']}")
        logger.debug(f"Available label IDs keys: {list(label_ids.keys())}")

        processed_label_id = label_ids.get(config.get(
            'labels', {}).get('processed', 'ProcessedByAgent'))
        if processed_label_id:
            tag_label_ids = []
            for tag in tagged_email['tags']:
                if tag in label_ids:
                    tag_label_ids.append(label_ids[tag])

            try:
                service = fetcher.gmail_services[email_data['account_id']]
                await asyncio.to_thread(
                    service.users().messages().modify(
                        userId='me',
                        id=email_data['id'],
                        body={'addLabelIds': [
                            processed_label_id] + tag_label_ids}
                    ).execute
                )
                logger.info("Email successfully marked as processed with tags")
            except Exception as e:
                logger.error(f"Error applying labels to email: {str(e)}")
        else:
            logger.warning("Warning: ProcessedByAgent label ID not found")

        return result

    except Exception as e:
        logger.exception(f"Error processing email: {str(e)}")
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
    logger.info(f"Processing batch of {len(email_batch)} emails")
    results = []

    # Step 1: Preprocess all emails in the batch
    preprocessed_batch = []
    for i, email in enumerate(email_batch):
        try:
            preprocessed = preprocessor.preprocess_email(email)
            preprocessed_batch.append(preprocessed)
        except Exception as e:
            logger.error(f"Error preprocessing email {i}: {str(e)}")
            # Add a placeholder to maintain index alignment
            preprocessed_batch.append(
                {'preprocessing_status': 'error', 'error_message': str(e)})

    # Step 2: Analyze all preprocessed emails in the batch
    analysis_results = []
    analysis_inputs = []

    for i, preprocessed in enumerate(preprocessed_batch):
        email = email_batch[i]
        if preprocessed['preprocessing_status'] == 'error':
            logger.error(
                f"Skipping analysis for email {i} due to preprocessing error")
            analysis_results.append(None)
            continue

        analysis_input = {
            'from': email['from'],
            'subject': email['subject'],
            'body': preprocessed['cleaned_body'],
            'received_date': email['date']
        }
        analysis_inputs.append(analysis_input)

    # Analyze all inputs in parallel
    if analysis_inputs:
        try:
            # Analyze emails in chunks to avoid overwhelming the LLM service
            chunk_size = 3
            for i in range(0, len(analysis_inputs), chunk_size):
                chunk = analysis_inputs[i:i + chunk_size]
                chunk_results = await asyncio.gather(
                    *[analyzer.analyze_email(input_data, timezone)
                      for input_data in chunk],
                    return_exceptions=True
                )

                for result in chunk_results:
                    if isinstance(result, Exception):
                        logger.error(f"Error analyzing email: {str(result)}")
                        analysis_results.append(None)
                    else:
                        analysis_results.append(result)
        except Exception as e:
            logger.error(f"Error during batch analysis: {str(e)}")
            # Fill the rest with None if there was an error
            analysis_results.extend(
                [None] * (len(analysis_inputs) - len(analysis_results)))

    # Step 3: Tag emails based on analysis
    tagged_emails = []
    for i, (email, analysis) in enumerate(zip(email_batch, analysis_results)):
        if analysis is None:
            # Add a placeholder to maintain index alignment
            tagged_emails.append(
                {'tagging_status': 'error', 'error_message': 'Analysis failed'})
            continue

        try:
            tagged_email = await tagger.tag_email(email, analysis)
            tagged_emails.append(tagged_email)
        except Exception as tag_e:
            logger.error(f"Error tagging email: {str(tag_e)}")
            # Add untagged email to maintain index alignment
            tagged_emails.append(
                {'tagging_status': 'error', 'error_message': str(tag_e)})

    # Step 4: Process the rest of the pipeline for each email
    for i, (preprocessed, analysis, tagged_email) in enumerate(zip(preprocessed_batch, analysis_results, tagged_emails)):
        if not analysis:
            logger.error(
                f"Error analyzing email: {email_batch[i].get('subject', 'No subject')}")
            continue

        logger.info(
            f"Processing email {i+1}/{len(email_batch)}: {email_batch[i].get('subject', 'No subject')}")

        email_data = email_batch[i]

        # Format result for this email
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
            'analysis': {
                'is_spam': analysis.get('is_spam', False),
                'category': analysis.get('category', 'UNKNOWN'),
                'priority': analysis.get('priority', 'NORMAL'),
                'reasoning': analysis.get('reasoning'),
                'tagging_status': tagged_email.get('tagging_status', 'unknown'),
                'tags': tagged_email.get('tags', [])
            }
        }

        # Process calendar events if needed
        if 'calendar' in analysis.get('required_tools', []) and analysis.get('calendar_event'):
            try:
                logger.info("Creating calendar event...")
                calendar_result = await calendar_agent.create_event(analysis['calendar_event'])
                result['calendar_result'] = calendar_result
            except Exception as e:
                logger.error(f"Error creating calendar event: {str(e)}")
                result['calendar_result'] = {
                    'status': 'error', 'error': str(e)}

        # Mark email as processed in Gmail
        try:
            processed_label_id = label_ids.get(config.get(
                'labels', {}).get('processed', 'ProcessedByAgent'))
            if processed_label_id:
                tag_label_ids = []
                for tag in tagged_email.get('tags', []):
                    if tag in label_ids:
                        tag_label_ids.append(label_ids[tag])

                service = fetcher.gmail_services[email_data['account_id']]
                await asyncio.to_thread(
                    service.users().messages().modify(
                        userId='me',
                        id=email_data['id'],
                        body={'addLabelIds': [
                            processed_label_id] + tag_label_ids}
                    ).execute
                )
                logger.info("Email successfully marked as processed with tags")
                result['tagging_result'] = {
                    'status': 'success', 'tags': tagged_email.get('tags', [])}
            else:
                logger.warning("Warning: ProcessedByAgent label ID not found")
                result['tagging_result'] = {
                    'status': 'error', 'error': 'ProcessedByAgent label ID not found'}
        except Exception as e:
            logger.error(f"Error tagging email: {str(e)}")
            result['tagging_result'] = {'status': 'error', 'error': str(e)}

        results.append(result)

    return results


async def run_pipeline(accounts_config: List[Dict[str, str]],
                       analyzer_type: str = None,
                       timezone: str = None,
                       batch_size: int = None):
    """Run the complete email processing pipeline for multiple accounts.

    Args:
        accounts_config: List of account configurations with credentials and token paths
        analyzer_type: Type of analyzer to use ('ollama' or 'lmstudio')
        timezone: Timezone for calendar events
        batch_size: Number of emails to process in a batch. If None, process one by one.
    """
    try:
        # Use config values if not overridden
        analyzer_type = analyzer_type or config.get("analyzer_type")
        timezone = timezone or config.get("timezone")
        batch_size = batch_size or config.get("batch_size")

        logger.info(
            f"Starting pipeline with analyzer_type={analyzer_type}, timezone={timezone}, batch_size={batch_size}")

        # Initialize components
        fetcher = EmailFetcher()
        preprocessor = EmailPreprocessor()
        # Update parameter name to use the same parameter name consistently
        analyzer = UnifiedEmailAnalyzer(backend=analyzer_type)
        calendar_agent = CalendarAgent()
        tagger = EmailTagger()

        # Setup Gmail clients for all accounts
        logger.info("Setting up Gmail clients...")
        for account in accounts_config:
            account_id = account.get('account_id', 'default')
            await fetcher.setup_gmail(
                account['credentials_path'],
                account['token_path'],
                account_id
            )

            # Initialize calendar service with same credentials
            logger.info(f"Setting up calendar service for {account_id}...")
            await calendar_agent.setup_calendar(
                account['credentials_path'],
                account['token_path'],
                account_id,
                account.get('timezone', timezone)
            )

        # Fetch unprocessed emails from all accounts
        logger.info("Fetching unprocessed emails from the last 24 hours...")
        all_emails = await fetcher.fetch_all_emails()

        if not all_emails:
            logger.info("No unprocessed emails found.")
            return

        logger.info(
            f"Found {len(all_emails)} unprocessed emails. Processing...")

        # Process emails from all accounts
        results = []

        # Determine processing method based on batch_size
        if batch_size and batch_size > 1:
            # Process emails in batches of the specified size
            for i in range(0, len(all_emails), batch_size):
                batch = all_emails[i:i+batch_size]
                logger.info(
                    f"Processing batch {i//batch_size + 1} ({len(batch)} emails)")

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
                logger.info(f"Processing email {i+1} of {len(all_emails)}")

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
        logger.info("=== Pipeline Summary ===")
        logger.info(f"Total emails processed: {len(results)}")
        logger.info(f"Successful: {len(results)}")
        logger.info(f"Failed: {len(all_emails) - len(results)}")

    except Exception as e:
        logger.exception(f"Pipeline Error: {str(e)}")


async def process_emails(accounts_file: str = None,
                         analyzer_type: str = None,
                         timezone: str = None,
                         batch_size: int = None):
    """Process emails using the pipeline.

    Args:
        accounts_file: Path to JSON file containing account configurations (overrides config)
        analyzer_type: Type of analyzer to use (overrides config)
        timezone: Timezone for calendar events (overrides config)
        batch_size: Number of emails to process in a batch (overrides config)
    """
    try:
        # Get project root directory
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))

        # Use provided accounts_file or get from config
        accounts_file = accounts_file or config.get("accounts_file")
        accounts_path = os.path.join(project_root, accounts_file)

        # Load accounts configuration
        with open(accounts_path) as f:
            account_config = json.load(f)
            accounts_config = account_config['accounts']

        # Resolve relative paths for credentials
        for account in accounts_config:
            account['credentials_path'] = os.path.join(
                project_root, account['credentials_path'])
            account['token_path'] = os.path.join(
                project_root, account['token_path'])

        # Run the pipeline
        await run_pipeline(
            accounts_config,
            analyzer_type=analyzer_type,
            timezone=timezone,
            batch_size=batch_size
        )

    except Exception as e:
        logger.exception(f"Error loading accounts configuration: {str(e)}")


def main():
    """Main entry point for the mail-agent command."""
    # Load environment variables
    load_dotenv()

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Mail Agent CLI')
    parser.add_argument('--version', action='store_true',
                        help='Show version information')
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
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )

    args = parser.parse_args()

    if args.version:
        from mail_agent import __version__
        print(f"Mail Agent version {__version__}")
        return

    if args.log_level:
        # Update log level if specified
        log_level = getattr(logging, args.log_level)
        logger.setLevel(log_level)
        # Update handlers
        for handler in logger.handlers:
            handler.setLevel(log_level)

    if args.process:
        # Process emails
        asyncio.run(
            process_emails(
                accounts_file=args.accounts,
                analyzer_type=args.analyzer,
                timezone=args.timezone,
                batch_size=args.batch_size
            )
        )
    else:
        # Show help if no action specified
        parser.print_help()


if __name__ == "__main__":
    sys.exit(main())
