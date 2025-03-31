"""Logging configuration for Mail Agent.

This module sets up logging for the application with appropriate handlers and formatters.
"""

import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from .config import config

# Create logs directory if it doesn't exist
logs_dir = Path(__file__).parent.parent / "logs"
logs_dir.mkdir(exist_ok=True)

# Configure logging
log_level = getattr(logging, config.get("log_level", "INFO"))
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"

# Create formatter
formatter = logging.Formatter(log_format, date_format)

# Create handlers
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Create rotating file handler (10MB max, keep 5 backup files)
file_handler = RotatingFileHandler(
    logs_dir / "mail_agent.log",
    maxBytes=10485760,  # 10MB
    backupCount=5
)
file_handler.setFormatter(formatter)


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger.

    Args:
        name: Name of the logger, typically the module name

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Add handlers if they haven't been added already
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    # Prevent log propagation to avoid duplicate logs
    logger.propagate = False

    return logger
