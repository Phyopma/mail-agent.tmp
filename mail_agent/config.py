"""Configuration manager for Mail Agent.

This module loads configuration from environment variables and config files,
and provides a centralized way to access configuration values.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Default configuration
DEFAULT_CONFIG = {
    "analyzer_type": "openrouter",  # Options: ollama, lmstudio, openrouter
    "timezone": "America/Los_Angeles",
    "batch_size": 0,
    "log_level": "INFO",
    "accounts_file": "accounts.json",
    "labels": {
        "processed": "ProcessedByAgent",
        "spam": "Spam",
        "work": "Work",
        "personal": "Personal",
        "important": "Important",
        "urgent": "Urgent"
    }
}


class ConfigManager:
    """Configuration manager for the application."""

    def __init__(self) -> None:
        """Initialize the configuration manager."""
        self.config = DEFAULT_CONFIG.copy()
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file if available."""
        # Get project root directory
        project_root = Path(__file__).parent.parent.absolute()
        config_path = project_root / "config.json"

        # Load from config file if it exists
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    file_config = json.load(f)
                    self.config.update(file_config)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config file: {e}")

        # Override with environment variables if they exist
        self._override_from_env()

    def _override_from_env(self) -> None:
        """Override configuration with environment variables."""
        # Map of env variable names to config keys
        env_map = {
            "MAIL_AGENT_ANALYZER": "analyzer_type",
            "MAIL_AGENT_TIMEZONE": "timezone",
            "MAIL_AGENT_BATCH_SIZE": "batch_size",
            "MAIL_AGENT_LOG_LEVEL": "log_level",
            "MAIL_AGENT_ACCOUNTS_FILE": "accounts_file",
        }

        for env_var, config_key in env_map.items():
            if env_var in os.environ:
                # Handle type conversion for numeric values
                if config_key == "batch_size":
                    try:
                        self.config[config_key] = int(os.environ[env_var])
                    except ValueError:
                        # Keep default if conversion fails
                        pass
                else:
                    self.config[config_key] = os.environ[env_var]

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: The configuration key to get
            default: Default value if key doesn't exist

        Returns:
            The configuration value or default
        """
        return self.config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values.

        Returns:
            Dictionary of all configuration values
        """
        return self.config.copy()

    def get_accounts_config(self) -> Dict[str, Any]:
        """Get accounts configuration.

        Returns:
            Dictionary of accounts configuration or empty dict if not found
        """
        accounts_file = self.get("accounts_file")
        project_root = Path(__file__).parent.parent.absolute()
        accounts_path = project_root / accounts_file

        if accounts_path.exists():
            try:
                with open(accounts_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading accounts file: {e}")
                return {}
        return {}


# Singleton instance
config = ConfigManager()
