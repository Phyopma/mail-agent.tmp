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
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from calendar_agent import CalendarAgent
from email_fetcher import EmailFetcher
from email_fetcher.google_service_manager import GoogleServiceManager
from email_preprocessor import EmailPreprocessor
from email_tagger import EmailTagger
from spam_detector import UnifiedEmailAnalyzer

from mail_agent.account_loader import load_accounts_config
from mail_agent.config import config
from mail_agent.graph import build_graph, make_initial_state
from mail_agent.logger import get_logger

logger = get_logger(__name__)


def _resolve_accounts_path(project_root: str, accounts_file: Optional[str]) -> str:
    """Resolve accounts config path from env/relative path with cloud-safe fallbacks."""
    configured = accounts_file or config.get("accounts_file") or "accounts.json"
    candidates = [
        configured,
        str(Path(configured)),
        str(Path(project_root) / configured),
        "/app/secrets/accounts/accounts.json",
        "/app/accounts.json",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            logger.info(f"Resolved accounts file: {candidate}")
            return candidate

    logger.error(f"Accounts file candidates checked: {candidates}")
    return candidates[0]


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
        raise


async def process_emails(
    accounts_file: Optional[str] = None,
    timezone: Optional[str] = None,
    batch_size: Optional[int] = None,
    target_account_id: Optional[str] = None,
) -> None:
    """Process emails using the pipeline."""
    try:
        accounts_config = load_accounts_config(accounts_file)
        requested_account_id = target_account_id or os.getenv("MAIL_AGENT_TARGET_ACCOUNT_ID")
        if requested_account_id:
            accounts_config = [
                account for account in accounts_config
                if account.get("account_id") == requested_account_id
            ]
            if not accounts_config:
                raise ValueError(f"Target account not found: {requested_account_id}")

        await run_pipeline(
            accounts_config,
            timezone=timezone,
            batch_size=batch_size,
        )

    except Exception as e:
        logger.exception(f"Error loading accounts configuration: {str(e)}")
        raise


async def renew_gmail_watches(accounts_file: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    """Renew Gmail watches for every configured account."""
    topic_name = config.get("gmail_watch_topic")
    if not topic_name:
        raise ValueError("MAIL_AGENT_GMAIL_WATCH_TOPIC or config.gmail_watch_topic must be set")

    results: List[Dict[str, Optional[str]]] = []
    service_manager = GoogleServiceManager()
    for account in load_accounts_config(accounts_file):
        account_id = account.get("account_id", "default")
        try:
            response = await service_manager.setup_gmail_watch(
                account["credentials_path"],
                account["token_path"],
                topic_name=topic_name,
                account_id=account_id,
            )
            history_id = response.get("historyId")
            expiration = response.get("expiration")
            logger.info(
                "Renewed Gmail watch for %s historyId=%s expiration=%s",
                account_id,
                history_id,
                expiration,
            )
            results.append(
                {
                    "account_id": account_id,
                    "history_id": history_id,
                    "expiration": expiration,
                    "error": None,
                }
            )
        except Exception as exc:
            logger.exception("Failed to renew Gmail watch for %s", account_id)
            results.append(
                {
                    "account_id": account_id,
                    "history_id": None,
                    "expiration": None,
                    "error": str(exc),
                }
            )
    failures = [result for result in results if result["error"]]
    if failures:
        failed_accounts = ", ".join(result["account_id"] for result in failures)
        raise RuntimeError(f"Failed to renew Gmail watches for: {failed_accounts}")
    return results


def main() -> None:
    """Main entry point for the mail-agent command."""
    load_dotenv()

    parser = argparse.ArgumentParser(description="Mail Agent CLI")
    parser.add_argument("--version", action="store_true", help="Show version information")
    parser.add_argument("--process", action="store_true", help="Process fetched emails")
    parser.add_argument("--renew-watches", action="store_true", help="Renew Gmail watches for all accounts")
    parser.add_argument("--account-id", type=str, help="Process only the specified account id")
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
                target_account_id=args.account_id,
            )
        )
    elif args.renew_watches:
        asyncio.run(renew_gmail_watches(accounts_file=args.accounts))
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.exit(main())
