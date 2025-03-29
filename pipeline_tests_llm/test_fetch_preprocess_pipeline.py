
#!/usr/bin/env python3

"""Integrated Email Processing Pipeline Test.

This script tests the complete email processing pipeline by:
1. Fetching emails from Gmail
2. Preprocessing the emails
3. Analyzing them for spam and categorization

It supports switching between different model backends for analysis.
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


async def run_pipeline(credentials_path: str, token_path: str, analyzer_type: str = 'ollama'):
    """Run the complete email processing pipeline.

    Args:
        credentials_path: Path to Gmail API credentials file
        token_path: Path to Gmail token file
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
            max_concurrent_requests=1  # Process one email at a time for clear output
        )
        tagger = EmailTagger()

        # Setup Gmail client
        print("Setting up Gmail client...")
        await fetcher.setup_gmail(credentials_path, token_path)

        # Fetch unprocessed emails
        print("\nFetching unprocessed emails from the last 24 hours...")
        emails = await fetcher.fetch_all_emails()

        emails = emails[:5]

        if not emails:
            print("No unprocessed emails found.")
            return

        print(f"\nFound {len(emails)} unprocessed emails. Processing...\n")

        # Get all required label IDs from the fetcher
        if 'default' not in fetcher.label_ids:
            print("Error: Label IDs not initialized")
            return
        
        label_ids = fetcher.label_ids['default']
        processed_label_id = label_ids.get('ProcessedByAgent')

        if not processed_label_id:
            print("Error: ProcessedByAgent label not found")
            return

        # Process each email
        for i, email in enumerate(emails, 1):
            print(f"Processing Email {i}/{len(emails)}:")
            print("-" * 60)
            print(f"From: {email['from']}")
            print(f"Subject: {email['subject']}")
            print(f"Date: {email['date']}")

            try:
                # Preprocess email
                print("\nPreprocessing...")
                preprocessed = preprocessor.preprocess_email(email)

                if preprocessed['preprocessing_status'] == 'error':
                    print(
                        f"Preprocessing Error: {preprocessed['error_message']}")
                    continue

                # Analyze email
                print("Analyzing...")
                analysis_result = await analyzer.analyze_email({
                    'from': email['from'],
                    'subject': email['subject'],
                    'body': preprocessed['cleaned_body']
                })

                if analysis_result:
                    # Format the complete result
                    result = {
                        'metadata': {
                            'email_id': email['id'],
                            'account_id': email['account_id'],
                            'timestamp': datetime.now(UTC).isoformat(),
                            'analyzer': analyzer_type
                        },
                        'email': {
                            'from': email['from'],
                            'subject': email['subject'],
                            'date': email['date'],
                            'body': preprocessed['cleaned_body']
                        },
                        'preprocessing': {
                            'status': preprocessed['preprocessing_status'],
                            'content_length': len(preprocessed['cleaned_body'])
                        },
                        'analysis': analysis_result
                    }

                    # Apply tags based on analysis
                    print("\nApplying tags...")
                    tagged_email = await tagger.tag_email(email, analysis_result)
                    result['tagging'] = tagged_email['tags']

                    # Print complete results including tags
                    print("\nProcessing Results:")
                    print(json.dumps(result, indent=2))

                    # Convert tag names to label IDs
                    tag_label_ids = []
                    for tag in tagged_email['tags']:
                        if tag in label_ids:
                            tag_label_ids.append(label_ids[tag])
                    
                    # Use the fetched label IDs
                    service = fetcher.gmail_services[email['account_id']]
                    # Mark email as processed with all labels
                    await asyncio.to_thread(
                        service.users().messages().modify(
                            userId='me',
                            id=email['id'],
                            body={'addLabelIds': [
                                processed_label_id] + tag_label_ids}
                        ).execute
                    )
                    print("Email marked as processed with tags")
                else:
                    print("Error: Analysis failed for this email")

            except Exception as e:
                print(f"Error processing email: {str(e)}")

            print("-" * 60 + "\n")

    except Exception as e:
        print(f"Pipeline Error: {str(e)}")


def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Email Spam Detection Pipeline Test')
    parser.add_argument(
        '--credentials',
        type=str,
        default='credentials/gmail_credentials.json',
        help='Path to Gmail API credentials file'
    )
    parser.add_argument(
        '--token',
        type=str,
        default='credentials/gmail_token.pickle',
        help='Path to Gmail token file'
    )
    parser.add_argument(
        '--analyzer',
        type=str,
        choices=['ollama', 'lmstudio'],
        default='ollama',
        help='Type of analyzer to use (ollama or lmstudio)'
    )

    args = parser.parse_args()

    # Run the pipeline with the selected analyzer
    asyncio.run(run_pipeline(args.credentials,
                args.token, analyzer_type=args.analyzer))


if __name__ == '__main__':
    main()
