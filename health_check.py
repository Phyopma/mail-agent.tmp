#!/usr/bin/env python3
"""Health check script for Mail Agent.

This script checks if:
1. The mail agent configuration is valid
2. The credentials are accessible
3. The LLM backend is responding

Usage:
    python health_check.py
"""

from spam_detector import UnifiedEmailAnalyzer
from email_fetcher import EmailFetcher
from mail_agent.logger import get_logger
from mail_agent.config import config
import os
import sys
import json
import argparse
import asyncio
import traceback
from datetime import datetime
from pathlib import Path
import dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


# Set up logger
logger = get_logger("health_check")

# Load environment variables from .env file if it exists
dotenv.load_dotenv(Path(__file__).parent / ".env")


async def check_credentials():
    """Check if credentials are valid and accessible."""
    try:
        # Get accounts configuration
        accounts_config = config.get_accounts_config()
        if not accounts_config or 'accounts' not in accounts_config:
            return False, "No accounts configured"

        fetcher = EmailFetcher()

        # Try to setup Gmail for each account
        for account in accounts_config['accounts']:
            account_id = account.get('account_id', 'default')
            creds_path = account['credentials_path']
            token_path = account['token_path']

            if not os.path.exists(creds_path):
                return False, f"Credentials file not found: {creds_path}"

            try:
                await fetcher.setup_gmail(creds_path, token_path, account_id)
                logger.info(
                    f"Successfully connected to Gmail for account: {account_id}")
            except Exception as e:
                error_trace = traceback.format_exc()
                logger.error(f"Gmail setup error: {error_trace}")
                return False, f"Failed to setup Gmail for account {account_id}: {str(e)}"

        return True, "Credentials are valid"
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Credentials check error: {error_trace}")
        return False, f"Error checking credentials: {str(e)}"


async def check_llm_backend():
    """Check if the LLM backend is responding."""
    try:
        model_name = config.get("gemini_model")
        logger.info(f"Testing Gemini model: {model_name}")

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return False, "GOOGLE_API_KEY not found in environment variables"
        logger.info("GOOGLE_API_KEY found in environment")

        analyzer = UnifiedEmailAnalyzer()

        # Simple test query
        test_data = {
            'from': 'test@example.com',
            'subject': 'Health Check Test',
            'body': 'This is a test email to check if the LLM backend is responding.',
            'received_date': datetime.now().isoformat()
        }

        logger.info(f"Sending test request to {model_name}")

        # Use a timeout to prevent long hangs
        try:
            result = await asyncio.wait_for(
                analyzer.analyze_email(test_data, config.get("timezone")),
                timeout=30  # 30 second timeout
            )
        except asyncio.TimeoutError:
            return False, f"Gemini model '{model_name}' timed out after 30 seconds"

        if result is None:
            logger.error(f"Gemini model '{model_name}' returned None")
            return False, f"Gemini model '{model_name}' failed to respond"

        logger.info(
            f"LLM backend responded with: {json.dumps(result, default=str)[:100]}...")
        return True, f"Gemini model '{model_name}' is responding properly"
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"LLM backend check error: {error_trace}")
        return False, f"Error checking LLM backend: {str(e)}"


async def check_configuration():
    """Check if the configuration is valid."""
    try:
        all_config = config.get_all()
        logger.info(
            f"Checking configuration: {json.dumps(all_config, indent=2)}")

        # Check required keys
        required_keys = ["timezone", "accounts_file", "gemini_model"]
        for key in required_keys:
            if key not in all_config:
                return False, f"Missing required configuration key: {key}"

        # Check if accounts file exists
        accounts_file = Path(all_config["accounts_file"])
        if not (Path(__file__).parent / accounts_file).exists():
            return False, f"Accounts file not found: {accounts_file}"

        return True, "Configuration is valid"
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Configuration check error: {error_trace}")
        return False, f"Error checking configuration: {str(e)}"


async def run_health_check(check_llm=True, verbose=False):
    """Run all health checks and return the results."""
    # Set log level to DEBUG if verbose is True
    if verbose:
        for handler in logger.handlers:
            handler.setLevel("DEBUG")
        logger.setLevel("DEBUG")

    results = {}

    # Check configuration
    config_result, config_message = await check_configuration()
    results["configuration"] = {
        "status": "OK" if config_result else "FAIL",
        "message": config_message
    }

    # Check credentials
    creds_result, creds_message = await check_credentials()
    results["credentials"] = {
        "status": "OK" if creds_result else "FAIL",
        "message": creds_message
    }

    # Check LLM backend if requested
    if check_llm:
        llm_result, llm_message = await check_llm_backend()
        results["llm_backend"] = {
            "status": "OK" if llm_result else "FAIL",
            "message": llm_message
        }

    # Determine overall status
    overall_status = "OK"
    for check, result in results.items():
        if result["status"] != "OK":
            overall_status = "FAIL"
            break

    results["overall"] = {
        "status": overall_status,
        "timestamp": datetime.now().isoformat()
    }

    return results


def main():
    """Main entry point for health check script."""
    parser = argparse.ArgumentParser(description="Mail Agent Health Check")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip LLM backend check (faster)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")

    args = parser.parse_args()

    results = asyncio.run(run_health_check(not args.skip_llm, args.verbose))

    if args.json:
        print(json.dumps(results, indent=2))
        sys.exit(0 if results["overall"]["status"] == "OK" else 1)

    # Pretty print results
    print("=== Mail Agent Health Check ===")
    print(f"Time: {results['overall']['timestamp']}")
    print(f"Overall Status: {results['overall']['status']}")
    print()

    for check, result in results.items():
        if check != "overall":
            status_str = "✅" if result["status"] == "OK" else "❌"
            print(f"{check.title()}: {status_str} - {result['message']}")

    sys.exit(0 if results["overall"]["status"] == "OK" else 1)


if __name__ == "__main__":
    main()
