# Mail Agent Deployment Guide

This guide explains how to deploy the Mail Agent application in a production environment.

## Prerequisites

- Python 3.8 or higher
- Access to Gmail API credentials
- Gemini API access (GOOGLE_API_KEY)

## Installation

1. Clone the repository:

   ```
   git clone <repository-url>
   cd mail-agent
   ```

2. Create a virtual environment and install dependencies:

   ```
   python -m venv venv
   source venv/bin/activate
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

- `MAIL_AGENT_GEMINI_MODEL`: Gemini model name (default: gemini-2.5-flash-lite)
- `MAIL_AGENT_GEMINI_TEMPERATURE`: Gemini temperature (default: 0.1)
- `MAIL_AGENT_GEMINI_MAX_OUTPUT_TOKENS`: Max output tokens (default: 2048)
- `MAIL_AGENT_GEMINI_TIMEOUT`: Gemini request timeout in seconds (default: 60)
- `MAIL_AGENT_TIMEZONE`: Default timezone for calendar events
- `MAIL_AGENT_BATCH_SIZE`: Number of emails to process in a batch
- `MAIL_AGENT_LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `MAIL_AGENT_ACCOUNTS_FILE`: Path to the accounts configuration file

Gemini requires:

- `GOOGLE_API_KEY`: Your Gemini API key

## Running the Application

### Manual Execution

Run the application manually:

## Cloud Run Job Deployment (Recommended)

This app runs best as a scheduled Cloud Run Job. You must generate OAuth tokens locally
before deploying (OAuth is interactive and cannot run in Cloud Run).

### 1) Build and push the container
```bash
export PROJECT_ID=your-project-id
export REGION=us-central1

gcloud auth configure-docker "$REGION-docker.pkg.dev"
gcloud artifacts repositories create mail-agent \
  --repository-format=docker \
  --location="$REGION"

docker build -t "$REGION-docker.pkg.dev/$PROJECT_ID/mail-agent/mail-agent:latest" .
docker push "$REGION-docker.pkg.dev/$PROJECT_ID/mail-agent/mail-agent:latest"
```

### 2) Create secrets
```bash
gcloud secrets create gmail-credentials --data-file=credentials/gmail_credentials.json
gcloud secrets create gmail-token --data-file=credentials/gmail_token.pickle
printf %s "$GOOGLE_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
```

### 3) Deploy the job
```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export SCHEDULER_SA=service-account@your-project-id.iam.gserviceaccount.com

./deploy.sh
```

Optional scheduler env vars:
```bash
export CREATE_SCHEDULER=true
export SCHEDULER_JOB=mail-agent-hourly
export SCHEDULE="0 * * * *"
```

### 4) Accounts config for Cloud Run
`deploy.sh` mounts secrets under `/app/secrets/*` and the app resolves those paths
automatically, so accounts can keep the same relative paths used locally:
```json
{
  "accounts": [
    {
      "account_id": "primary",
      "credentials_path": "credentials/gmail_credentials.json",
      "token_path": "credentials/gmail_token.pickle",
      "timezone": "America/Los_Angeles",
      "email": "you@example.com"
    }
  ]
}
```

### 5) Schedule with Cloud Scheduler (optional)
```bash
gcloud scheduler jobs create http mail-agent-hourly \
  --schedule="0 * * * *" \
  --uri="https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT/jobs/mail-agent-job:run" \
  --http-method=POST \
  --oauth-service-account-email=SERVICE_ACCOUNT@PROJECT.iam.gserviceaccount.com
```

## Troubleshooting

If you encounter issues during deployment, consider the following troubleshooting steps:

1. **Check Environment Variables**: Ensure all required environment variables are set correctly.
2. **Verify Credentials**: Make sure your Gmail API credentials are correctly placed in the `credentials` directory.
3. **Review Logs**: Check the application logs for any error messages or warnings.
4. **Network Issues**: Ensure your network allows access to the required APIs.
5. **Dependencies**: Verify that all dependencies are installed correctly in your virtual environment.
6. **Configuration Files**: Double-check your `config.json` and `accounts.json` files for any misconfigurations.

If the issue persists, consult the application's documentation or seek help from the community.
