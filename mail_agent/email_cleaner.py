"""Email Cleaner Module for Mail Agent.

This module handles automatic email deletion based on retention policies.
It runs as a separate scheduled job to enforce cleanup rules.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Optional
import asyncio
from email_fetcher import EmailFetcher
from mail_agent.logger import get_logger

logger = get_logger(__name__)


class EmailCleaner:
    """Handles email cleanup based on retention policies."""

    # Protected categories that get longer retention
    PROTECTED_CATEGORIES: Set[str] = {"Work", "Personal", "School"}

    # Retention rules: (priority, category_condition, max_age_days)
    # category_condition: None = any, "protected" = in PROTECTED_CATEGORIES, "unprotected" = not in
    RETENTION_RULES = [
        # Priority Ignore: Delete immediately
        {"priority": "Ignore", "category": None, "max_age_days": 0},
        # Priority Low + Unprotected: Delete after 3 days
        {"priority": "Low", "category": "unprotected", "max_age_days": 3},
        # Priority Low + Protected: Delete after 14 days
        {"priority": "Low", "category": "protected", "max_age_days": 14},
        # Priority Normal + Unprotected: Delete after 7 days
        {"priority": "Normal", "category": "unprotected", "max_age_days": 7},
        # Priority Normal + Protected: Delete after 14 days
        {"priority": "Normal", "category": "protected", "max_age_days": 14},
    ]

    def __init__(self, fetcher: EmailFetcher):
        """Initialize the email cleaner.
        
        Args:
            fetcher: EmailFetcher instance with initialized Gmail services
        """
        self.fetcher = fetcher
        self.deleted_count = 0
        self.skipped_count = 0
        # Cache for label ID -> name mapping per account
        self._label_cache: Dict[str, Dict[str, str]] = {}

    def _parse_priority_from_labels(self, labels: List[str]) -> Optional[str]:
        """Extract priority from Gmail labels.
        
        Args:
            labels: List of label names
            
        Returns:
            Priority string (Ignore, Low, Normal, High, etc.) or None
        """
        for label in labels:
            if label.startswith("Priority/"):
                return label.split("/")[1]
        return None

    def _parse_category_from_labels(self, labels: List[str]) -> Optional[str]:
        """Extract category from Gmail labels.
        
        Args:
            labels: List of label names
            
        Returns:
            Category string or None
        """
        for label in labels:
            if label.startswith("Category/"):
                return label.split("/")[1]
        return None

    def _is_protected_category(self, category: Optional[str]) -> bool:
        """Check if category is protected.
        
        Args:
            category: Category string
            
        Returns:
            True if protected, False otherwise
        """
        if not category:
            return False
        return category.title() in self.PROTECTED_CATEGORIES

    def _should_delete(
        self, priority: Optional[str], category: Optional[str], email_age_days: float
    ) -> bool:
        """Determine if an email should be deleted based on retention rules.
        
        Args:
            priority: Email priority
            category: Email category
            email_age_days: Age of email in days
            
        Returns:
            True if email should be deleted
        """
        if not priority:
            return False

        priority_normalized = priority.title()
        is_protected = self._is_protected_category(category)

        for rule in self.RETENTION_RULES:
            if rule["priority"] != priority_normalized:
                continue

            # Check category condition
            if rule["category"] == "protected" and not is_protected:
                continue
            if rule["category"] == "unprotected" and is_protected:
                continue

            # Check age
            if email_age_days >= rule["max_age_days"]:
                return True

        return False

    async def get_emails_for_cleanup(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch emails that have been processed and may need cleanup.
        
        Args:
            account_id: Gmail account identifier
            
        Returns:
            List of email metadata dicts
        """
        gmail_service = self.fetcher.gmail_services.get(account_id)
        if not gmail_service:
            logger.error(f"No Gmail service for account {account_id}")
            return []

        # Cache label mapping once per account
        if account_id not in self._label_cache:
            await self._cache_labels(gmail_service, account_id)

        # Query for emails with ProcessedByAgent label
        query = "label:ProcessedByAgent"
        
        try:
            results = await asyncio.to_thread(
                gmail_service.users().messages().list(userId="me", q=query, maxResults=500).execute
            )
            messages = results.get("messages", [])
            total = len(messages)
            logger.info(f"Found {total} processed emails for account {account_id}")
            
            emails = []
            for idx, msg in enumerate(messages):
                # Progress logging every 50 emails
                if (idx + 1) % 50 == 0 or idx == 0:
                    logger.info(f"Fetching email details: {idx + 1}/{total}")
                
                # Get full message to access labels and headers
                full_msg = await asyncio.to_thread(
                    gmail_service.users().messages().get(
                        userId="me", id=msg["id"], format="metadata",
                        metadataHeaders=["Date"]
                    ).execute
                )
                
                # Extract label names using cache
                label_ids = full_msg.get("labelIds", [])
                label_names = self._get_label_names_from_cache(account_id, label_ids)
                
                # Extract date
                headers = full_msg.get("payload", {}).get("headers", [])
                date_header = next(
                    (h["value"] for h in headers if h["name"].lower() == "date"),
                    None
                )
                
                emails.append({
                    "id": msg["id"],
                    "account_id": account_id,
                    "labels": label_names,
                    "date": date_header,
                    "internal_date": full_msg.get("internalDate"),
                })
            
            logger.info(f"Finished fetching {total} email details")
            return emails
            
        except Exception as e:
            logger.error(f"Error fetching emails for cleanup: {e}")
            return []

    async def _cache_labels(self, gmail_service, account_id: str) -> None:
        """Cache label ID to name mapping for an account.
        
        Args:
            gmail_service: Gmail API service
            account_id: Account identifier
        """
        try:
            logger.info(f"Caching labels for account {account_id}...")
            labels_response = await asyncio.to_thread(
                gmail_service.users().labels().list(userId="me").execute
            )
            self._label_cache[account_id] = {
                l["id"]: l["name"] for l in labels_response.get("labels", [])
            }
            logger.info(f"Cached {len(self._label_cache[account_id])} labels")
        except Exception as e:
            logger.error(f"Error caching labels: {e}")
            self._label_cache[account_id] = {}

    def _get_label_names_from_cache(self, account_id: str, label_ids: List[str]) -> List[str]:
        """Convert label IDs to names using cached mapping.
        
        Args:
            account_id: Account identifier
            label_ids: List of label IDs
            
        Returns:
            List of label names
        """
        cache = self._label_cache.get(account_id, {})
        return [cache.get(lid, lid) for lid in label_ids]

    async def delete_email(self, account_id: str, email_id: str, dry_run: bool = False) -> bool:
        """Delete a single email.
        
        Args:
            account_id: Gmail account identifier
            email_id: Email message ID
            dry_run: If True, log but don't actually delete
            
        Returns:
            True if deleted (or would be deleted in dry run)
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would delete email {email_id}")
            return True
            
        gmail_service = self.fetcher.gmail_services.get(account_id)
        if not gmail_service:
            return False
            
        try:
            await asyncio.to_thread(
                gmail_service.users().messages().trash(userId="me", id=email_id).execute
            )
            logger.info(f"Trashed email {email_id}")
            return True
        except Exception as e:
            logger.error(f"Error trashing email {email_id}: {e}")
            return False

    async def run_cleanup(self, dry_run: bool = False) -> Dict[str, int]:
        """Run the cleanup process for all accounts.
        
        Args:
            dry_run: If True, log actions but don't delete
            
        Returns:
            Dict with deleted and skipped counts
        """
        self.deleted_count = 0
        self.skipped_count = 0
        now = datetime.now(timezone.utc)

        for account_id in self.fetcher.gmail_services:
            logger.info(f"Running cleanup for account {account_id}")
            emails = await self.get_emails_for_cleanup(account_id)
            
            for email in emails:
                # Parse labels
                labels = email.get("labels", [])
                priority = self._parse_priority_from_labels(labels)
                category = self._parse_category_from_labels(labels)
                
                # Calculate age
                internal_date_ms = email.get("internal_date")
                if internal_date_ms:
                    email_date = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
                    age_days = (now - email_date).total_seconds() / 86400
                else:
                    age_days = 0
                
                # Check if should delete
                if self._should_delete(priority, category, age_days):
                    success = await self.delete_email(account_id, email["id"], dry_run)
                    if success:
                        self.deleted_count += 1
                        logger.info(
                            f"{'[DRY RUN] ' if dry_run else ''}Deleted: {email['id']} "
                            f"(Priority={priority}, Category={category}, Age={age_days:.1f}d)"
                        )
                else:
                    self.skipped_count += 1

        return {
            "deleted": self.deleted_count,
            "skipped": self.skipped_count,
        }
