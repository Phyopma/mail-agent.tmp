"""Pipeline test for Email Fetcher and Preprocessor integration.

This script demonstrates the complete flow from fetching emails to preprocessing them,
showing how the components work together in the pipeline.
"""

from email_preprocessor import EmailPreprocessor
from email_fetcher import EmailFetcher
from spam_detector import SpamDetector
import os
import sys
import json
import asyncio

from pathlib import Path

# Add the parent directory to the Python path
parent_dir = Path(__file__).resolve().parent.parent


async def test_pipeline():
    """Run the email fetching and preprocessing pipeline."""
    try:
        # Initialize components
        fetcher = EmailFetcher()
        preprocessor = EmailPreprocessor()
        spam_detector = SpamDetector()

        # Setup Gmail credentials
        credentials_path = os.path.join(
            parent_dir, 'credentials', 'gmail_credentials.json')
        token_path = os.path.join(
            parent_dir, 'credentials', 'gmail_token.pickle')

        print('Setting up Gmail connection...')
        await fetcher.setup_gmail(credentials_path, token_path)

        # Fetch emails
        print('\nFetching emails...')
        emails = await fetcher.fetch_all_emails()
        print(f'Found {len(emails)} unprocessed emails')

        # Process emails and show results immediately
        print('\nProcessing emails and formatting for LLM:')
        print('-' * 50)

        for i, email in enumerate(emails, 1):
            print(f'\nProcessing Email {i}/{len(emails)}...')

            # Process email
            processed = preprocessor.preprocess_email(email)

            # Initialize the result format
            llm_format = {
                'metadata': {
                    'email_id': email['id'],
                    'thread_id': email['thread_id'],
                    'account': email['account_id'],
                    'provider': email['provider'],
                    'timestamp': email['date'],
                    'processing_status': processed['preprocessing_status']
                },
                'email': {
                    'from': email['from'],
                    'subject': email['subject'],
                    'content': processed['cleaned_body'] if processed['preprocessing_status'] == 'success' else ''
                },
                'error': processed.get('error_message') if processed['preprocessing_status'] == 'error' else None
            }

            # Perform spam detection if preprocessing was successful
            if processed['preprocessing_status'] == 'success':
                print('\nPerforming spam detection...')
                spam_result = await spam_detector.detect_spam({
                    'from': email['from'],
                    'subject': email['subject'],
                    'body': processed['cleaned_body']
                })
                llm_format['spam_analysis'] = spam_result
            else:
                llm_format['spam_analysis'] = {
                    'is_spam': None,
                    'confidence': 0.0,
                    'reasoning': 'Spam analysis skipped due to preprocessing error'
                }

            # Print results
            print('\nProcessing Result:')
            print(json.dumps(llm_format, indent=2))
            print('-' * 50)

    except Exception as e:
        print(f'Pipeline error: {str(e)}')

if __name__ == '__main__':
    asyncio.run(test_pipeline())
