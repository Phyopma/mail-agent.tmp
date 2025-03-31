@echo off
REM Run script for Mail Agent (Windows)

REM Set up environment
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist venv (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    call venv\Scripts\activate
    pip install -e .
) else (
    call venv\Scripts\activate
)

REM Run the Mail Agent
python -m mail_agent.main --process

pause
