#!/usr/bin/env python3
"""Main entry point for the Mail Agent CLI.

This module implements the email processing pipeline:
1. Fetch emails from Gmail accounts
2. Preprocess content
3. Analyze with Gemini via LangChain
4. Apply actions (calendar/tasks/reminders)
5. Tag and mark emails as processed
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv

from calendar_agent import CalendarAgent
from email_fetcher import EmailFetcher
from email_preprocessor import EmailPreprocessor
from email_tagger import EmailTagger
from spam_detector import UnifiedEmailAnalyzer

from mail_agent.config import config
from mail_agent.graph import build_graph, make_initial_state
from mail_agent.logger import get_logger

logger = get_logger(__name__)


async def run_pipeline(
    accounts_config: List[Dict[str, str]],
    timezone: Optional[str] = None,
    batch_size: Optional[int] = None,
) -> None:
    """Run the complete email processing pipeline for multiple accounts."""
    try:
        timezone = timezone or config.get("timezone")
        batch_size = batch_size or config.get("batch_size")

        logger.info(
            f"Starting pipeline with timezone={timezone}, batch_size={batch_size}")

        fetcher = EmailFetcher()
        preprocessor = EmailPreprocessor()
        analyzer = UnifiedEmailAnalyzer()
        calendar_agent = CalendarAgent()
        tagger = EmailTagger()

        logger.info("Setting up Gmail clients...")
        account_timezones: Dict[str, str] = {}
        for account in accounts_config:
            account_id = account.get("account_id", "default")
            account_timezones[account_id] = account.get("timezone", timezone)
            await fetcher.setup_gmail(
                account["credentials_path"],
                account["token_path"],
                account_id,
            )

            logger.info(f"Setting up calendar service for {account_id}...")
            await calendar_agent.setup_calendar(
                account["credentials_path"],
                account["token_path"],
                account_id,
                account_timezones[account_id],
            )

        logger.info("Fetching unprocessed emails from the last 24 hours...")
        all_emails = await fetcher.fetch_all_emails()

        if not all_emails:
            logger.info("No unprocessed emails found.")
            return

        logger.info(f"Found {len(all_emails)} unprocessed emails. Processing...")

        app = build_graph(preprocessor, analyzer, calendar_agent, tagger, fetcher)

        results = []
        chunk_size = batch_size if batch_size and batch_size > 1 else 1

        async def invoke_graph(state):
            if hasattr(app, "ainvoke"):
                return await app.ainvoke(state)
            return await asyncio.to_thread(app.invoke, state)

        for i in range(0, len(all_emails), chunk_size):
            chunk = all_emails[i:i + chunk_size]
            tasks = []
            for email in chunk:
                account_id = email.get("account_id", "default")
                label_ids = fetcher.label_ids.get(account_id, {})
                initial_state = make_initial_state(
                    email, label_ids, account_timezones.get(account_id, timezone)
                )
                tasks.append(invoke_graph(initial_state))

            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"Graph execution error: {result}")
                    continue
                results.append(result)

        logger.info("=== Pipeline Summary ===")
        logger.info(f"Total emails processed: {len(results)}")
        logger.info(f"Successful: {len([r for r in results if r.get('processed')])}")
        logger.info(f"Failed: {len(all_emails) - len([r for r in results if r.get('processed')])}")

    except Exception as e:
        logger.exception(f"Pipeline Error: {str(e)}")


async def process_emails(
    accounts_file: Optional[str] = None,
    timezone: Optional[str] = None,
    batch_size: Optional[int] = None,
) -> None:
    """Process emails using the pipeline."""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        accounts_file = accounts_file or config.get("accounts_file")
        accounts_path = os.path.join(project_root, accounts_file)

        with open(accounts_path) as f:
            account_config = json.load(f)
            accounts_config = account_config["accounts"]

        for account in accounts_config:
            account["credentials_path"] = os.path.join(
                project_root, account["credentials_path"]
            )
            account["token_path"] = os.path.join(
                project_root, account["token_path"]
            )

        await run_pipeline(
            accounts_config,
            timezone=timezone,
            batch_size=batch_size,
        )

    except Exception as e:
        logger.exception(f"Error loading accounts configuration: {str(e)}")


def main() -> None:
    """Main entry point for the mail-agent command."""
    load_dotenv()

    parser = argparse.ArgumentParser(description="Mail Agent CLI")
    parser.add_argument("--version", action="store_true", help="Show version information")
    parser.add_argument("--process", action="store_true", help="Process fetched emails")
    parser.add_argument("--accounts", type=str, help="JSON file containing account configurations")
    parser.add_argument(
        "--timezone",
        type=str,
        default="America/Los_Angeles",
        help="Timezone for calendar events",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Number of emails to process concurrently.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    args = parser.parse_args()

    if args.version:
        from mail_agent import __version__

        print(f"Mail Agent version {__version__}")
        return

    if args.log_level:
        log_level = getattr(logging, args.log_level)
        logger.setLevel(log_level)
        for handler in logger.handlers:
            handler.setLevel(log_level)

    if args.process:
        asyncio.run(
            process_emails(
                accounts_file=args.accounts,
                timezone=args.timezone,
                batch_size=args.batch_size,
            )
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.exit(main())
