"""Configuration settings for Email Fetcher module.

This module contains placeholder configurations for Gmail API credentials.
Replace these values with your actual credentials.
"""

# Gmail API credentials for multiple accounts
GMAIL_CONFIG = {
    "default": {
        "credentials_file": "credentials/gmail_credentials.json",
        "token_file": "path/to/your/gmail_token.pickle"
    },
    # Add more accounts as needed:
    "work": {
        "credentials_file": "credentials/gmail_credentials.json",
        "token_file": "path/to/work_gmail_token.pickle"
    }
}

# Email processing settings
EMAIL_SETTINGS = {
    "processed_tag": "ProcessedByAgent",
    "fetch_interval_hours": 24
}
