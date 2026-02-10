#!/usr/bin/env python3
"""Cleanup Data Entry Point for Mail Agent.

This script runs the email cleanup process based on retention policies.
It is designed to run as a separate Cloud Run Job on a daily schedule.

Usage:
    python cleanup_data.py [--dry-run]

Options:
    --dry-run   Log which emails would be deleted without actually deleting them
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from email_fetcher import EmailFetcher
from mail_agent.email_cleaner import EmailCleaner
from mail_agent.config import config
from mail_agent.logger import get_logger

logger = get_logger(__name__)


async def main(dry_run: bool = False):
    """Main cleanup function.
    
    Args:
        dry_run: If True, only log actions without deleting
    """
    logger.info("=" * 50)
    logger.info("Mail Agent Cleanup Started")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info("=" * 50)
    
    # Load account configurations
    accounts_config = config.get_accounts_config()
    accounts = accounts_config.get("accounts", [])
    
    if not accounts:
        logger.error("No accounts configured in accounts.json")
        return
    
    # Initialize fetcher and setup Gmail services
    fetcher = EmailFetcher()
    
    for account in accounts:
        account_id = account.get("account_id", account.get("id", "default"))
        credentials_path = account.get("credentials_path", "credentials/gmail_credentials.json")
        token_path = account.get("token_path", "credentials/gmail_token.pickle")
        
        try:
            logger.info(f"Setting up Gmail for account: {account_id}")
            await fetcher.setup_gmail(credentials_path, token_path, account_id)
        except Exception as e:
            logger.error(f"Failed to setup account {account_id}: {e}")
            continue
    
    if not fetcher.gmail_services:
        logger.error("No Gmail services initialized")
        return
    
    # Run cleanup
    cleaner = EmailCleaner(fetcher)
    results = await cleaner.run_cleanup(dry_run=dry_run)
    
    logger.info("=" * 50)
    logger.info("Cleanup Complete")
    logger.info(f"Deleted: {results['deleted']}")
    logger.info(f"Skipped: {results['skipped']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mail Agent Cleanup")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log which emails would be deleted without actually deleting them"
    )
    args = parser.parse_args()
    
    asyncio.run(main(dry_run=args.dry_run))
