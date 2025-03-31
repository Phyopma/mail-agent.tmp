#!/usr/bin/env python3
"""Update script for Mail Agent.

This script helps update the Mail Agent codebase and dependencies.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(command, check=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(command, shell=True,
                                check=check, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error: {e.stderr.strip()}")
        if check:
            sys.exit(1)
        return None


def update_git_repo():
    """Update the git repository."""
    print("Checking for updates...")

    # Check if we're in a git repository
    if not Path(".git").exists():
        print("Error: Not a git repository. Please run this script from the mail-agent directory.")
        sys.exit(1)

    # Fetch the latest changes
    run_command("git fetch")

    # Check if we're behind the remote
    status = run_command("git status -uno")
    if "Your branch is up to date" in status:
        print("Your code is already up to date.")
        return False

    # Stash any local changes
    print("Stashing local changes...")
    run_command("git stash")

    # Pull the latest changes
    print("Updating code...")
    run_command("git pull")

    # Apply stashed changes if any
    stash_list = run_command("git stash list")
    if stash_list:
        print("Applying stashed changes...")
        run_command("git stash pop", check=False)

    return True


def update_dependencies():
    """Update Python dependencies."""
    print("Updating dependencies...")

    # Check if requirements.txt exists
    if Path("requirements.txt").exists():
        run_command("pip install --upgrade -r requirements.txt")
    else:
        # Reinstall the package
        run_command("pip install --upgrade -e .")

    print("Dependencies updated successfully.")


def restart_services():
    """Restart Mail Agent services if running as a service."""
    # Check if systemd service exists
    if Path("/etc/systemd/system/mail-agent.service").exists():
        print("Restarting Mail Agent systemd service...")
        run_command("sudo systemctl restart mail-agent.timer", check=False)
        run_command("sudo systemctl restart mail-agent.service", check=False)
    else:
        print("No systemd service found. Please restart Mail Agent manually if needed.")


def main():
    """Main entry point for update script."""
    parser = argparse.ArgumentParser(description="Update Mail Agent")
    parser.add_argument("--no-restart", action="store_true",
                        help="Don't restart services after update")
    parser.add_argument("--dependencies-only", action="store_true",
                        help="Only update dependencies, not the code")

    args = parser.parse_args()

    # Change to the script's directory
    os.chdir(Path(__file__).parent)

    if not args.dependencies_only:
        updated = update_git_repo()
    else:
        updated = False

    # Always update dependencies
    update_dependencies()

    if updated and not args.no_restart:
        restart_services()

    print("Update completed successfully.")


if __name__ == "__main__":
    main()
