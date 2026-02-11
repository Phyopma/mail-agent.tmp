# Mail Agent Architecture

Last updated: 2026-02-10

## Overview
Mail Agent is a Python CLI that fetches unread Gmail messages, cleans the content, runs Gemini-based LLM analysis for spam/category/priority and action extraction, then tags emails and optionally creates Google Calendar events, reminders, or tasks. The system uses Gmail labels to mark processed emails instead of a database and relies on Google APIs plus LangGraph orchestration.

## High-Level Flow
```mermaid
flowchart LR
    A[Gmail API] --> B[EmailFetcher]
    B --> C[LangGraph Pipeline]
    C --> D[EmailPreprocessor]
    C --> E[Gemini Analyzer]
    E --> L[Classification Gate]
    L -->|Spam| M[Immediate Trash]
    L -->|Not Spam| F[EmailTagger]
    C --> G[CalendarAgent]
    F --> H[Gmail Labels]
    G --> I[Google Calendar / Tasks]
    J[Config + .env] --> C
    K[Logger] --> C
```

## Runtime Entry Points
- CLI: `mail_agent/main.py` orchestrates account setup, fetches emails, and runs the LangGraph pipeline per email.
- Test harness: `pipeline_tests_llm/test_fetch_preprocess_pipeline.py` exercises fetch → preprocess → analyze → tag.

## Core Components

### 1) Pipeline Orchestrator (LangGraph)
- File: `mail_agent/graph.py`
- Graph nodes:
  - `preprocess`: cleans and normalizes email content
  - `analyze`: Gemini-based analysis with text-first structured output + multimodal fallback + deterministic heuristic fallback
  - `validate_classification`: enforces complete classification contract (spam/category/priority)
  - `spam_disposition`: immediately trashes spam emails (configurable)
  - `decide_actions`: gates actions by priority and category
  - `execute_actions`: creates calendar events, reminders, and tasks
  - `apply_tags`: applies standardized Gmail labels
  - `mark_processed`: adds `ProcessedByAgent` only when required category and priority tags are both present and resolved

### 2) Gmail Integration
- File: `email_fetcher/email_fetcher.py`
- Fetches unprocessed emails from the last 24 hours.
- Uses Gmail label `ProcessedByAgent` to skip processed items.
- Recursively extracts `text/plain` or `text/html` parts and collects non-text attachment metadata (`attachment_id`, `filename`, `mime_type`, `size`, `inline_data_b64`).

### 3) Google API Setup
- File: `email_fetcher/google_service_manager.py`
- Handles OAuth tokens and initializes Gmail, Calendar, and Tasks services.
- Creates required Gmail labels if missing.

### 4) Preprocessing
- File: `email_preprocessor/email_preprocessor.py`
- Decodes base64 body, strips HTML, removes URLs, signatures, disclaimers, and emojis.
- Normalizes whitespace for LLM input.
- Produces `text_length` and `body_quality` (`full_text`, `short_text`, `no_text`) for classifier fallback routing.

### 5) LLM Analysis (Gemini)
- File: `spam_detector/unified_email_analyzer.py`
- Uses LangChain `ChatGoogleGenerativeAI` with Gemini Developer API.
- Enforces structured Pydantic output for analysis results.
- Uses staged fallback: text structured analysis, multimodal structured analysis (attachments), then deterministic heuristic fallback.
- Guarantees classification metadata fields: `classification_source` and `classification_complete`.

### 6) Tagging
- File: `email_tagger/email_tagger.py`
- Converts enum results to Gmail labels:
  - `Priority/<Level>`
  - `Category/<Type>`

### 7) Calendar/Tasks Actions
- File: `calendar_agent/calendar_agent.py`
- Creates Google Calendar events and Google Tasks items.
- Converts timestamps into account timezone using `zoneinfo`.

### 8) Configuration and Logging
- Config: `mail_agent/config.py`
  - Gemini model configuration, timezone, and batch size.
- Logging: `mail_agent/logger.py`
  - Console + rotating file handler at `logs/mail_agent.log`.

## Data Contracts

### Preprocessing Output
```json
{
  "cleaned_body": "...",
  "text_length": 1234,
  "body_quality": "full_text|short_text|no_text",
  "preprocessing_status": "success|error",
  "error_message": "..."
}
```

### LLM Analysis Output
```json
{
  "is_spam": "SPAM|NOT_SPAM",
  "category": "WORK|PERSONAL|FAMILY|SOCIAL|MARKETING|SCHOOL|NEWSLETTER|SHOPPING",
  "priority": "CRITICAL|URGENT|HIGH|NORMAL|LOW|IGNORE",
  "classification_source": "llm_text|llm_multimodal|heuristic",
  "classification_complete": true,
  "required_tools": ["calendar|reminder|task|none"],
  "calendar_event": {"title": "...", "start_time": "..."} | null,
  "reminder": {"title": "...", "due_date": "..."} | null,
  "task": {"title": "...", "due_date": "..."} | null,
  "reasoning": "..."
}
```

## State and Persistence
- Processed state is tracked via Gmail labels (no database).
- OAuth tokens are stored as pickled files per account.
- Logs are stored in `logs/`.

## Known Risks
- Gemini structured output may fail validation for rare inputs; analyzer now falls back to deterministic heuristics to keep classification complete.
- Gmail payloads vary; multipart parsing is best-effort and may still miss edge cases.
