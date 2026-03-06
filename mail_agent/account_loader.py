"""Helpers for loading Mail Agent account configuration consistently."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mail_agent.config import config


def resolve_accounts_path(accounts_file: Optional[str] = None) -> str:
    """Resolve the accounts file path with local and Cloud Run fallbacks."""
    configured = accounts_file or config.get("accounts_file") or "accounts.json"
    project_root = Path(__file__).parent.parent.absolute()
    candidates = [
        configured,
        str(Path(configured)),
        str(project_root / configured),
        "/app/secrets/accounts/accounts.json",
        "/app/accounts.json",
    ]

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    return candidates[0]


def load_accounts_config(accounts_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load accounts configuration and normalize credential/token paths."""
    accounts_path = resolve_accounts_path(accounts_file)
    with open(accounts_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if isinstance(raw, dict):
        accounts = raw.get("accounts", [])
    else:
        accounts = raw

    base_dir = Path(accounts_path).parent
    project_root = Path(__file__).parent.parent.absolute()
    normalized_accounts: List[Dict[str, Any]] = []
    for account in accounts:
        normalized = dict(account)
        for key in ("credentials_path", "token_path"):
            value = normalized.get(key)
            if value and not os.path.isabs(value):
                candidates = [
                    (base_dir / value).resolve(),
                    (project_root / value).resolve(),
                ]
                resolved = next((candidate for candidate in candidates if candidate.exists()), None)
                normalized[key] = str(resolved) if resolved else value
        normalized_accounts.append(normalized)

    return normalized_accounts


def build_account_email_map(accounts_config: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map lower-cased account email addresses to account config."""
    mapping: Dict[str, Dict[str, Any]] = {}
    for account in accounts_config:
        email = (account.get("email") or "").strip().lower()
        if email:
            mapping[email] = account
    return mapping
