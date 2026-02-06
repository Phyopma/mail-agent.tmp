# AGENTS

This file is a concise guide for AI or human contributors working on this repository.

## Project Summary
Mail Agent is a Python CLI that fetches Gmail messages, preprocesses content, runs LLM analysis for spam/category/priority and tool actions, tags emails in Gmail, and optionally creates Calendar/Tasks items.

## Key Entry Points
- CLI: `mail_agent/main.py`
- Unified LLM analyzer: `spam_detector/unified_email_analyzer.py`
- Gmail fetcher: `email_fetcher/email_fetcher.py`
- Google API setup: `email_fetcher/google_service_manager.py`
- Preprocessor: `email_preprocessor/email_preprocessor.py`
- Calendar/Tasks actions: `calendar_agent/calendar_agent.py`

## Local Setup
- Python 3.8+
- Install: `pip install -e .`
- Configure:
  - `config.json` (copy from `config.template.json`)
  - `accounts.json` (copy from `accounts.template.json`)
  - Gmail/Calendar credentials in `credentials/`

## Run
- `python -m mail_agent.main --process`
- Optional flags:
  - `--accounts <path>`
  - `--analyzer ollama|lmstudio|openrouter|groq`
  - `--batch-size <n>`
  - `--timezone <tz>`

## Testing Notes
- Tests exist under `email_fetcher/`, `email_preprocessor/`, `calendar_agent/`, and `pipeline_tests_llm/`.
- Many tests assume live Google credentials; avoid running in CI without secrets.

## Operational Constraints
- Gmail state is tracked via labels, not a database.
- Tokens are stored as pickled files; treat credentials and tokens as sensitive.
- The LLM integration uses OpenAI-compatible APIs and expects JSON outputs.

## Known Hotspots
- `spam_detector/unified_email_analyzer.py` is the core integration point for changing LLM providers.
- `mail_agent/main.py` contains batch/single processing logic and label application.
- `calendar_agent/calendar_agent.py` owns event/task creation and timezone handling.

## Contribution Guidelines
- Keep changes isolated per module; avoid cross-module coupling unless necessary.
- Prefer async-safe patterns for I/O calls (use `asyncio.to_thread` as in the codebase).
- Update `architecture.md` if you change major flows or dependencies.

