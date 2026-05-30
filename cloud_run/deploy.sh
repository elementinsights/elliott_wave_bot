#!/bin/bash
set -e

# Always run from this script's own directory so the relative paths below resolve.
cd "$(dirname "$0")"

PROJECT_ID="absolute-theme-497607-e6"
REGION="us-central1"
SERVICE_NAME="elliott-wave"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Telegram config — set these env vars before running
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN env var}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:?Set TELEGRAM_CHAT_ID env var}"
GOOGLE_SHEET_ID="${GOOGLE_SHEET_ID:?Set GOOGLE_SHEET_ID env var}"

SA_KEY_PATH="${1:-../service_account.json}"
if [ ! -f "$SA_KEY_PATH" ]; then
    echo "ERROR: Service account key not found at $SA_KEY_PATH"
    echo "Usage: ./deploy.sh [path_to_service_account.json]"
    exit 1
fi

echo "=== Elliott Wave Cloud Run Deploy ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo ""

# Copy files into cloud_run/ for Docker build context
echo "1. Copying files for build..."
cp ../ew_scanner_v2.py .
cp ../ew_monitor.py .
cp "$SA_KEY_PATH" service_account.json

# Build and push
echo "2. Building Docker image..."
gcloud builds submit --tag "${IMAGE}" --project "${PROJECT_ID}" --timeout=1200

# Deploy Cloud Run service
echo "3. Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --platform managed \
    --memory 2Gi \
    --timeout 3600 \
    --concurrency 1 \
    --max-instances 1 \
    --min-instances 0 \
    --no-allow-unauthenticated \
    --service-account "elliott-wave@${PROJECT_ID}.iam.gserviceaccount.com" \
    --set-env-vars="^||^TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}||TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}||GOOGLE_SHEET_ID=${GOOGLE_SHEET_ID}||MIN_SCORE=95||SETUP_FILTERS=WAVE_3,WAVE_5||REGIME_FILTER=true||POSITION_PCT=${POSITION_PCT:-0.05}||ACCOUNT_SIZE=${ACCOUNT_SIZE:-0}"

# Get service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" --project "${PROJECT_ID}" \
    --format 'value(status.url)')
echo "Service URL: ${SERVICE_URL}"

SA_EMAIL="elliott-wave@${PROJECT_ID}.iam.gserviceaccount.com"

# Create Cloud Scheduler jobs
echo "4. Setting up Cloud Scheduler..."

# Scanner: daily at 4:30 PM ET (21:30 UTC)
gcloud scheduler jobs delete "ew-daily-scan" \
    --location "${REGION}" --project "${PROJECT_ID}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http "ew-daily-scan" \
    --location "${REGION}" \
    --project "${PROJECT_ID}" \
    --schedule "30 16 * * 1-5" \
    --time-zone "America/New_York" \
    --uri "${SERVICE_URL}/scan" \
    --http-method GET \
    --oidc-service-account-email "${SA_EMAIL}" \
    --oidc-token-audience "${SERVICE_URL}" \
    --attempt-deadline 1800s \
    --description "Daily EWT scan after market close (4:30 PM ET)"

# Monitor: every 30 minutes during market hours, weekdays only
gcloud scheduler jobs delete "ew-monitor" \
    --location "${REGION}" --project "${PROJECT_ID}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http "ew-monitor" \
    --location "${REGION}" \
    --project "${PROJECT_ID}" \
    --schedule "*/30 9-16 * * 1-5" \
    --time-zone "America/New_York" \
    --uri "${SERVICE_URL}/monitor" \
    --http-method GET \
    --oidc-service-account-email "${SA_EMAIL}" \
    --oidc-token-audience "${SERVICE_URL}" \
    --attempt-deadline 300s \
    --description "EWT entry monitor every 30 min during market hours"

# Clean up copied files from build context
rm -f ew_scanner_v2.py ew_monitor.py service_account.json

echo ""
echo "=== Deploy complete ==="
echo "Service:  ${SERVICE_URL}"
echo "Scanner:  daily at 4:30 PM ET (Mon-Fri)"
echo "Monitor:  every 30 min during market hours (Mon-Fri)"
echo ""
echo "Test endpoints:"
echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" ${SERVICE_URL}/"
echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" ${SERVICE_URL}/monitor"
echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" ${SERVICE_URL}/scan"
