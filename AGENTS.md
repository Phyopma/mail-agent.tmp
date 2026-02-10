# AGENTS

This file is a concise guide for AI or human contributors working on this repository.

## Project Summary
Mail Agent is a Python CLI that fetches Gmail messages, preprocesses content, runs Gemini-based LLM analysis for spam/category/priority and tool actions, tags emails in Gmail, and optionally creates Calendar/Tasks items. The runtime pipeline is orchestrated with LangGraph and now enforces strict classification completeness.

## Key Entry Points
- CLI: `mail_agent/main.py`
- LangGraph pipeline: `mail_agent/graph.py`
- Unified LLM analyzer: `spam_detector/unified_email_analyzer.py`
- Gmail fetcher: `email_fetcher/email_fetcher.py`
- Google API setup: `email_fetcher/google_service_manager.py`
- Preprocessor: `email_preprocessor/email_preprocessor.py`
- Calendar/Tasks actions: `calendar_agent/calendar_agent.py`
- Tagging contract: `email_tagger/email_tagger.py`
- Cleanup job: `mail_agent/email_cleaner.py`

## Local Setup
- Python 3.8+
- Install: `pip install -e .`
- Configure:
  - `config.json` (copy from `config.template.json`)
  - `accounts.json` (copy from `accounts.template.json`)
  - Gmail/Calendar credentials in `credentials/`
  - `GOOGLE_API_KEY` for Gemini

## Run
- `python -m mail_agent.main --process`
- Optional flags:
  - `--accounts <path>`
  - `--batch-size <n>`
  - `--timezone <tz>`

## Testing Notes
- Unit tests include reliability coverage under `tests/`.
- Run targeted reliability tests:
  - `.venv/bin/python -m unittest tests.test_email_tagger_strict tests.test_email_fetcher_non_text tests.test_unified_email_analyzer_fallback tests.test_graph_reliability -v`
- Many tests assume live Google credentials; avoid running in CI without secrets.

## Operational Constraints
- Gmail state is tracked via labels, not a database.
- Tokens are stored as pickled files; treat credentials and tokens as sensitive.
- The LLM integration uses Gemini via LangChain and expects structured Pydantic outputs.

## Reliability Invariants (Do Not Break)
- Non-spam emails must not be marked `ProcessedByAgent` unless both labels are present and mapped:
  - `Priority/<...>`
  - `Category/<...>`
- Spam handling is owned by classifier pipeline (`mail_agent/graph.py`) and should trash immediately when configured.
- Analyzer output must include:
  - `classification_source` (`llm_text`, `llm_multimodal`, `heuristic`)
  - `classification_complete` (bool)
- If LLM output is incomplete or unavailable, analyzer must provide deterministic heuristic fallback classification.
- Fetcher must preserve attachment metadata for non-text content:
  - `attachment_id`, `filename`, `mime_type`, `size`, `inline_data_b64`
  - `has_non_text_content`

## Known Hotspots
- `mail_agent/graph.py` defines the LangGraph node flow and reliability gates.
- `spam_detector/unified_email_analyzer.py` is the core Gemini integration.
- `calendar_agent/calendar_agent.py` owns event/task creation and timezone handling.

## Pipeline Notes
- Graph nodes now include validation and spam branching:
  - `preprocess` -> `analyze` -> `validate_classification`
  - `validate_classification` routes to `spam_disposition` for spam or to normal action/tag flow for non-spam
- Cleaner (`mail_agent/email_cleaner.py`) remains independent and acts as retention job, with optional spam failsafe cleanup.

## Config Flags To Respect
- `enable_multimodal_fallback`
- `enforce_both_labels`
- `spam_disposition` (`trash` or `none`)
- `cleanup_spam_failsafe`
- `multimodal_max_attachments`
- `multimodal_max_attachment_bytes`

## Contribution Guidelines
- Keep changes isolated per module; avoid cross-module coupling unless necessary.
- Prefer async-safe patterns for I/O calls (use `asyncio.to_thread` as in the codebase).
- Update `architecture.md` if you change major flows or dependencies.
- Preserve the reliability invariants above when changing fetcher, analyzer, tagger, graph, or cleaner.
