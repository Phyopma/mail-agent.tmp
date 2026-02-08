#!/usr/bin/env python3

"""Integrated Email Processing Pipeline Test.

This script tests the pipeline by:
1. Fetching emails from Gmail
2. Preprocessing emails
3. Analyzing them with Gemini via LangChain
4. Applying tags and marking as processed
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone

from email_fetcher import EmailFetcher
from email_preprocessor import EmailPreprocessor
from email_tagger import EmailTagger
from spam_detector import UnifiedEmailAnalyzer


async def run_pipeline(credentials_path: str, token_path: str) -> None:
    try:
        print("\n=== Starting Email Processing Pipeline ===")

        fetcher = EmailFetcher()
        preprocessor = EmailPreprocessor()
        analyzer = UnifiedEmailAnalyzer(max_concurrent_requests=1)
        tagger = EmailTagger()

        print("Setting up Gmail client...")
        await fetcher.setup_gmail(credentials_path, token_path)

        print("\nFetching unprocessed emails from the last 24 hours...")
        emails = await fetcher.fetch_all_emails()
        emails = emails[:5]

        if not emails:
            print("No unprocessed emails found.")
            return

        print(f"\nFound {len(emails)} unprocessed emails. Processing...\n")

        if 'default' not in fetcher.label_ids:
            print("Error: Label IDs not initialized")
            return

        label_ids = fetcher.label_ids['default']
        processed_label_id = label_ids.get('ProcessedByAgent')

        if not processed_label_id:
            print("Error: ProcessedByAgent label not found")
            return

        for i, email in enumerate(emails, 1):
            print(f"Processing Email {i}/{len(emails)}:")
            print("-" * 60)
            print(f"From: {email['from']}")
            print(f"Subject: {email['subject']}")
            print(f"Date: {email['date']}")

            try:
                print("\nPreprocessing...")
                preprocessed = preprocessor.preprocess_email(email)

                if preprocessed['preprocessing_status'] == 'error':
                    print(f"Preprocessing Error: {preprocessed['error_message']}")
                    continue

                print("Analyzing...")
                analysis_result = await analyzer.analyze_email({
                    'from': email['from'],
                    'subject': email['subject'],
                    'body': preprocessed['cleaned_body'],
                    'received_date': email['date'],
                })

                if analysis_result:
                    result = {
                        'metadata': {
                            'email_id': email['id'],
                            'account_id': email['account_id'],
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                        },
                        'email': {
                            'from': email['from'],
                            'subject': email['subject'],
                            'date': email['date'],
                            'body': preprocessed['cleaned_body'],
                        },
                        'preprocessing': {
                            'status': preprocessed['preprocessing_status'],
                            'content_length': len(preprocessed['cleaned_body']),
                        },
                        'analysis': analysis_result,
                    }

                    print("\nApplying tags...")
                    tagged_email = await tagger.tag_email(email, analysis_result)
                    result['tagging'] = tagged_email['tags']

                    print("\nProcessing Results:")
                    print(json.dumps(result, indent=2))

                    tag_label_ids = []
                    for tag in tagged_email['tags']:
                        if tag in label_ids:
                            tag_label_ids.append(label_ids[tag])

                    service = fetcher.gmail_services[email['account_id']]
                    await asyncio.to_thread(
                        service.users().messages().modify(
                            userId='me',
                            id=email['id'],
                            body={'addLabelIds': [processed_label_id] + tag_label_ids},
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


def main() -> None:
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

    args = parser.parse_args()

    asyncio.run(run_pipeline(args.credentials, args.token))


if __name__ == '__main__':
    main()
