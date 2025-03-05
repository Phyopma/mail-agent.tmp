"""CLI for testing the Email Preprocessor module independently.

This script provides a command-line interface for testing the email preprocessor
with sample email data.
"""

import argparse
import json
import base64
from email_preprocessor import EmailPreprocessor

def create_sample_email(content: str, is_html: bool = False) -> dict:
    """Create a sample email dictionary with base64 encoded content.

    Args:
        content: Raw email content
        is_html: Whether the content is HTML

    Returns:
        Dictionary containing sample email data
    """
    if is_html:
        content = f"<html><body>{content}</body></html>"
    
    encoded_content = base64.urlsafe_b64encode(content.encode('utf-8')).decode('utf-8')
    
    return {
        'id': 'sample_1',
        'provider': 'test',
        'subject': 'Test Email',
        'from': 'test@example.com',
        'body': encoded_content
    }

def main():
    parser = argparse.ArgumentParser(description='Test Email Preprocessor')
    parser.add_argument('--content', type=str, default='Hello, this is a test email!',
                      help='Email content to process')
    parser.add_argument('--html', action='store_true',
                      help='Treat input as HTML content')
    
    args = parser.parse_args()
    
    # Create sample email
    email_data = create_sample_email(args.content, args.html)
    
    # Initialize preprocessor
    preprocessor = EmailPreprocessor()
    
    # Process email
    result = preprocessor.preprocess_email(email_data)
    
    # Print results
    print('\nProcessing Results:')
    print('-' * 50)
    print(f"Status: {result['preprocessing_status']}")
    if result['preprocessing_status'] == 'error':
        print(f"Error: {result['error_message']}")
    else:
        print('\nCleaned Content:')
        print('-' * 50)
        print(result['cleaned_body'])

if __name__ == '__main__':
    main()