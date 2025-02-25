"""Pipeline test for Email Fetcher and Preprocessor integration.

This script demonstrates the complete flow from fetching emails to preprocessing them,
showing how the components work together in the pipeline.
"""

from pathlib import Path
import sys
import os
import asyncio

# Set up parent directory path
parent_dir = str(Path(__file__).parent.parent.absolute())
sys.path.append(parent_dir)

# Import after setting up path
from email_fetcher import EmailFetcher
from email_preprocessor import EmailPreprocessor


async def test_pipeline():
    """Run the email fetching and preprocessing pipeline."""
    try:
        # Initialize components
        fetcher = EmailFetcher()
        preprocessor = EmailPreprocessor()

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

        # Process each email
        print('\nProcessing emails:')
        print('-' * 50)

        for i, email in enumerate(emails, 1):
            print(f'\nProcessing email {i}/{len(emails)}')
            print(f'Subject: {email.get("subject", "No subject")}')

            # Preprocess email
            processed = preprocessor.preprocess_email(email)

            # Print results
            print(f'Status: {processed["preprocessing_status"]}')
            if processed['preprocessing_status'] == 'error':
                print(
                    f'Error: {processed.get("error_message", "Unknown error")}')
            else:
                print('\nCleaned Content Preview:')
                content = processed['cleaned_body']
                # preview = content[:200] + '...' if len(content) > 200 else content
                preview = content
                print(preview)

            print('-' * 50)
    except Exception as e:
        print(f'Pipeline error: {str(e)}')

if __name__ == '__main__':
    asyncio.run(test_pipeline())
