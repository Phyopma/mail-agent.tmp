# Mail Agent Deployment Guide

This guide explains how to deploy the Mail Agent application in a production environment.

## Prerequisites

- Python 3.8 or higher
- Access to Gmail API credentials
- (Optional) Access to a local LLM service (Ollama) or an OpenRouter API key

## Installation

1. Clone the repository:

   ```
   git clone <repository-url>
   cd mail-agent
   ```

2. Create a virtual environment and install dependencies:

   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .
   ```

3. Set up configuration:

   - Copy `config.template.json` to `config.json` and edit as needed
   - Copy `accounts.template.json` to `accounts.json` and configure your accounts

4. Set up credentials:
   - Create a `credentials` directory
   - Place your Gmail API credentials in this directory (see below for instructions)

## Gmail API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Gmail API and Google Calendar API
4. Create OAuth 2.0 credentials
5. Download the credentials JSON file and save it to the `credentials` directory
6. When you first run the application, it will prompt you to authorize access

## Environment Variables

You can configure the application using environment variables:

- `MAIL_AGENT_ANALYZER`: Type of analyzer to use (ollama, lmstudio, openrouter)
- `MAIL_AGENT_TIMEZONE`: Default timezone for calendar events
- `MAIL_AGENT_BATCH_SIZE`: Number of emails to process in a batch
- `MAIL_AGENT_LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `MAIL_AGENT_ACCOUNTS_FILE`: Path to the accounts configuration file

For OpenRouter or other APIs:

- `OPENROUTER_API_KEY`: Your OpenRouter API key
- `GROQ_API_KEY`: Your Groq API key (if using Groq)

## Running the Application

### Manual Execution

Run the application manually:

## Troubleshooting

If you encounter issues during deployment, consider the following troubleshooting steps:

1. **Check Environment Variables**: Ensure all required environment variables are set correctly.
2. **Verify Credentials**: Make sure your Gmail API credentials are correctly placed in the `credentials` directory.
3. **Review Logs**: Check the application logs for any error messages or warnings.
4. **Network Issues**: Ensure your network allows access to the required APIs.
5. **Dependencies**: Verify that all dependencies are installed correctly in your virtual environment.
6. **Configuration Files**: Double-check your `config.json` and `accounts.json` files for any misconfigurations.

If the issue persists, consult the application's documentation or seek help from the community.
