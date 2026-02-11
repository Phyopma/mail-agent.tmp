#!/usr/bin/env bash
set -euo pipefail

# Load environment variables from .env and deploy.env
if [ -f .env ]; then source .env; fi
if [ -f deploy.env ]; then source deploy.env; fi

PROJECT_ID=${PROJECT_ID:-"YOUR_PROJECT_ID"}
REGION=${REGION:-"us-central1"}
REPO=${REPO:-"mail-agent"}
IMAGE_NAME=${IMAGE_NAME:-"mail-agent"}
TAG=${TAG:-"latest"}
JOB_NAME=${JOB_NAME:-"mail-agent-job"}
CREATE_SCHEDULER=${CREATE_SCHEDULER:-"true"}
SCHEDULER_JOB=${SCHEDULER_JOB:-"mail-agent-hourly"}
SCHEDULE=${SCHEDULE:-"0 * * * *"}
SCHEDULER_SA=${SCHEDULER_SA:-""}

IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE_NAME:$TAG"

if [[ "$PROJECT_ID" == "YOUR_PROJECT_ID" ]]; then
  echo "Please set PROJECT_ID environment variable."
  exit 1
fi

# Ensure artifact registry repo exists
echo "Checking Artifact Registry repository..."
if ! gcloud artifacts repositories describe "$REPO" --location "$REGION"; then
  echo "Repository not found (or error occurred). Attempting creation..."
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location="$REGION"
fi

echo "Configuring docker auth..."
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

if docker info >/dev/null 2>&1; then
  echo "Building Docker image for linux/amd64..."
  docker build --platform linux/amd64 --provenance=false -t "$IMAGE_URI" .
  echo "Pushing Docker image..."
  docker push "$IMAGE_URI"
else
  echo "Docker daemon unavailable. Falling back to Cloud Build..."
  gcloud services enable cloudbuild.googleapis.com --quiet
  gcloud builds submit --tag "$IMAGE_URI" .
fi

# Create or update secrets (expects local files)
echo "Updating secrets..."
if [[ -f credentials/gmail_credentials.json ]]; then
  echo "Updating gmail-credentials..."
  gcloud secrets describe gmail-credentials || gcloud secrets create gmail-credentials
  gcloud secrets versions add gmail-credentials --data-file=credentials/gmail_credentials.json
else
  echo "Missing credentials/gmail_credentials.json"
  exit 1
fi

if [[ -f credentials/gmail_token.pickle ]]; then
  echo "Updating gmail-token..."
  gcloud secrets describe gmail-token || gcloud secrets create gmail-token
  gcloud secrets versions add gmail-token --data-file=credentials/gmail_token.pickle
else
  echo "Missing credentials/gmail_token.pickle"
  exit 1
fi

if [[ -f credentials/uci_token.pickle ]]; then
  echo "Updating uci-token..."
  gcloud secrets describe uci-token || gcloud secrets create uci-token
  gcloud secrets versions add uci-token --data-file=credentials/uci_token.pickle
else
  echo "Warning: credentials/uci_token.pickle not found but might be needed."
fi

if [[ -n "${GOOGLE_API_KEY:-}" ]]; then
  echo "Updating gemini-api-key..."
  gcloud secrets describe gemini-api-key || gcloud secrets create gemini-api-key
  printf %s "$GOOGLE_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
else
  echo "Missing GOOGLE_API_KEY in environment"
  exit 1
fi

# Create/update the main job with minimal config, then set secrets via CLI
echo "Preparing Job configuration..."

if ! gcloud run jobs describe "$JOB_NAME" --region "$REGION" 2>/dev/null; then
  echo "Job $JOB_NAME does not exist. Creating..."
  gcloud run jobs create "$JOB_NAME" --image "$IMAGE_URI" --region "$REGION"
else
  echo "Updating job image..."
  gcloud run jobs update "$JOB_NAME" --image "$IMAGE_URI" --region "$REGION"
fi

echo "Ensuring Service Account permissions..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Granting Secret Accessor role to $COMPUTE_SA..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$COMPUTE_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet

# Configure secrets with distinct mount directories per secret to satisfy Cloud Run
# mount constraints while preserving app path resolution fallbacks.
echo "Configuring secrets for main job..."
gcloud run jobs update "$JOB_NAME" --region "$REGION" --clear-secrets
SECRET_MOUNTS="/app/secrets/gmail-creds/gmail_credentials.json=gmail-credentials:latest,/app/secrets/gmail-token/gmail_token.pickle=gmail-token:latest,GOOGLE_API_KEY=gemini-api-key:latest"
if gcloud secrets describe uci-token >/dev/null 2>&1; then
  SECRET_MOUNTS="$SECRET_MOUNTS,/app/secrets/uci-token/uci_token.pickle=uci-token:latest"
fi
gcloud run jobs update "$JOB_NAME" --region "$REGION" \
  --set-secrets="$SECRET_MOUNTS"
echo "Deployed Cloud Run Job: $JOB_NAME"

# Deploy Cleanup Job
CLEANUP_JOB_NAME="mail-agent-cleanup"
echo "Preparing Cleanup Job configuration..."

if ! gcloud run jobs describe "$CLEANUP_JOB_NAME" --region "$REGION" 2>/dev/null; then
  echo "Job $CLEANUP_JOB_NAME does not exist. Creating..."
  gcloud run jobs create "$CLEANUP_JOB_NAME" --image "$IMAGE_URI" --region "$REGION" --command="python,cleanup_data.py"
else
  echo "Updating cleanup job image..."
  gcloud run jobs update "$CLEANUP_JOB_NAME" --image "$IMAGE_URI" --region "$REGION" --command="python,cleanup_data.py"
fi

# Configure secrets for cleanup job.
echo "Configuring secrets for cleanup job..."
gcloud run jobs update "$CLEANUP_JOB_NAME" --region "$REGION" --clear-secrets
gcloud run jobs update "$CLEANUP_JOB_NAME" --region "$REGION" \
  --set-secrets="$SECRET_MOUNTS"
echo "Deployed Cloud Run Job: $CLEANUP_JOB_NAME"

# Configure Schedulers
if [[ "$CREATE_SCHEDULER" == "true" ]]; then
  if [[ -z "$SCHEDULER_SA" ]]; then
    echo "Skipping Cloud Scheduler creation (SCHEDULER_SA is not set)."
    echo "Set SCHEDULER_SA to a service account email to enable scheduling."
    exit 0
  fi

  # Main job scheduler (hourly)
  SCHEDULER_URI="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run"

  echo "Configuring Cloud Scheduler for main job (hourly)..."
  if gcloud scheduler jobs describe "$SCHEDULER_JOB" --location "$REGION" 2>/dev/null; then
    gcloud scheduler jobs update http "$SCHEDULER_JOB" \
      --location="$REGION" \
      --schedule="$SCHEDULE" \
      --uri="$SCHEDULER_URI" \
      --http-method=POST \
      --oauth-service-account-email="$SCHEDULER_SA"
  else
    gcloud scheduler jobs create http "$SCHEDULER_JOB" \
      --location="$REGION" \
      --schedule="$SCHEDULE" \
      --uri="$SCHEDULER_URI" \
      --http-method=POST \
      --oauth-service-account-email="$SCHEDULER_SA"
  fi
  echo "Scheduler job configured: $SCHEDULER_JOB ($SCHEDULE)"

  # Cleanup job scheduler (daily at midnight)
  CLEANUP_SCHEDULER_JOB="mail-agent-cleanup-daily"
  CLEANUP_SCHEDULE="0 0 * * *"
  CLEANUP_SCHEDULER_URI="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$CLEANUP_JOB_NAME:run"

  echo "Configuring Cloud Scheduler for cleanup job (daily)..."
  if gcloud scheduler jobs describe "$CLEANUP_SCHEDULER_JOB" --location "$REGION" 2>/dev/null; then
    gcloud scheduler jobs update http "$CLEANUP_SCHEDULER_JOB" \
      --location="$REGION" \
      --schedule="$CLEANUP_SCHEDULE" \
      --uri="$CLEANUP_SCHEDULER_URI" \
      --http-method=POST \
      --oauth-service-account-email="$SCHEDULER_SA"
  else
    gcloud scheduler jobs create http "$CLEANUP_SCHEDULER_JOB" \
      --location="$REGION" \
      --schedule="$CLEANUP_SCHEDULE" \
      --uri="$CLEANUP_SCHEDULER_URI" \
      --http-method=POST \
      --oauth-service-account-email="$SCHEDULER_SA"
  fi
  echo "Cleanup scheduler job configured: $CLEANUP_SCHEDULER_JOB ($CLEANUP_SCHEDULE)"
fi

echo "Deployment complete!"
