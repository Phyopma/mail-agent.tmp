# Mail Agent

An intelligent email processing system that automatically categorizes emails, detects important information, and performs actions like creating calendar events.

## Features

- **Email Processing**: Fetches and processes emails from Gmail
- **AI-Powered Analysis**: Uses LLM to categorize emails and determine priority
- **Smart Actions**: Detects deadlines and creates calendar events
- **Tagging**: Tags emails by category (Work, Personal, Spam, etc.)
- **Multi-Account Support**: Process emails from multiple Gmail accounts
- **Flexible LLM Backend**: Works with Ollama (local), LM Studio, or OpenRouter

## Requirements

- Python 3.8+
- Gmail API credentials
- Calendar API credentials
- LLM access (local or API-based)

## Quick Start

1. **Setup**:

   ```bash
   # Clone and install
   git clone <repository-url>
   cd mail-agent
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .

   # Setup configuration
   cp config.template.json config.json
   cp accounts.template.json accounts.json
   ```

2. **Configure accounts**:

   - Edit `accounts.json` with your Gmail account information
   - Place your Gmail API credentials in the `credentials` directory

3. **Run the agent**:
   ```bash
   mail_agent --process
   ```

## Configuration

Mail Agent can be configured through `config.json` or environment variables:

| Config Key    | Environment Variable  | Description                                |
| ------------- | --------------------- | ------------------------------------------ |
| analyzer_type | MAIL_AGENT_ANALYZER   | LLM backend (ollama, lmstudio, openrouter) |
| timezone      | MAIL_AGENT_TIMEZONE   | Default timezone for calendar events       |
| batch_size    | MAIL_AGENT_BATCH_SIZE | Number of emails to process at once        |
| log_level     | MAIL_AGENT_LOG_LEVEL  | Logging level (DEBUG, INFO, etc.)          |

## Deployment

For production deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).

## License

[MIT License](LICENSE)
