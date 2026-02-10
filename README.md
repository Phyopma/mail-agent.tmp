# Mail Agent

An intelligent email processing system that automatically categorizes emails, detects important information, and performs actions like creating calendar events.

## Features

- **Email Processing**: Fetches and processes emails from Gmail
- **AI-Powered Analysis**: Uses LLM to categorize emails and determine priority
- **Smart Actions**: Detects deadlines and creates calendar events
- **Tagging**: Tags emails by category (Work, Personal, Spam, etc.)
- **Multi-Account Support**: Process emails from multiple Gmail accounts
- **Gemini LLM Backend**: Uses Gemini via LangChain (Google GenAI)
- **LangGraph Orchestration**: Structured, node-based pipeline with retries

## Requirements

- Python 3.8+
- Gmail API credentials
- Calendar API credentials
- Gemini API access (GOOGLE_API_KEY)

## Quick Start

1. **Setup**:

   ```bash
   # Clone and install
   git clone <repository-url>
   cd mail-agent
   python -m venv venv
   source venv/bin/activate
   pip install -e .

   # Setup configuration
   cp config.template.json config.json
   cp accounts.template.json accounts.json
   ```

2. **Configure accounts**:

   - Edit `accounts.json` with your Gmail account information
   - Place your Gmail API credentials in the `credentials` directory

3. **Set Gemini API key**:
   ```bash
   export GOOGLE_API_KEY=your_api_key
   ```

4. **Run the agent**:
   ```bash
   mail_agent --process
   ```

## Configuration

Mail Agent can be configured through `config.json` or environment variables. Gemini requires `GOOGLE_API_KEY`:

| Config Key                | Environment Variable                  | Description                                     |
| ------------------------- | ------------------------------------- | ----------------------------------------------- |
| gemini_model              | MAIL_AGENT_GEMINI_MODEL               | Gemini model name (default: gemini-2.5-flash-lite) |
| gemini_temperature        | MAIL_AGENT_GEMINI_TEMPERATURE         | Gemini temperature (default: 0.1)               |
| gemini_max_output_tokens  | MAIL_AGENT_GEMINI_MAX_OUTPUT_TOKENS   | Max output tokens (default: 2048)               |
| gemini_timeout            | MAIL_AGENT_GEMINI_TIMEOUT             | Gemini request timeout in seconds (default: 60) |
| enable_multimodal_fallback | MAIL_AGENT_ENABLE_MULTIMODAL_FALLBACK | Enable image/PDF-aware fallback when text body is weak |
| enforce_both_labels       | MAIL_AGENT_ENFORCE_BOTH_LABELS        | Require both category and priority labels before marking processed |
| spam_disposition          | MAIL_AGENT_SPAM_DISPOSITION           | Spam handling mode (`trash` or `none`)          |
| cleanup_spam_failsafe     | MAIL_AGENT_CLEANUP_SPAM_FAILSAFE      | Cleaner job deletes residual spam-labeled mail  |
| multimodal_max_attachments | MAIL_AGENT_MULTIMODAL_MAX_ATTACHMENTS | Max attachments sent to multimodal classifier     |
| multimodal_max_attachment_bytes | MAIL_AGENT_MULTIMODAL_MAX_ATTACHMENT_BYTES | Max bytes per attachment for multimodal fallback |
| timezone                  | MAIL_AGENT_TIMEZONE                   | Default timezone for calendar events            |
| batch_size                | MAIL_AGENT_BATCH_SIZE                 | Number of emails to process at once             |
| log_level                 | MAIL_AGENT_LOG_LEVEL                  | Logging level (DEBUG, INFO, etc.)               |

## Deployment

For production deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).

## License

[MIT License](LICENSE)
