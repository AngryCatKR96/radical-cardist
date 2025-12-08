#!/bin/bash

# Cloud Run Backend (FastAPI) Deployment Script
# Usage: ./deploy-backend.sh

set -e

echo "🚀 Starting backend deployment to Cloud Run..."

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE_NAME="${BACKEND_SERVICE_NAME:-cardemon-backend}"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI is not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if project ID is set
if [ "$PROJECT_ID" = "your-gcp-project-id" ]; then
    echo "⚠️  Warning: Please set GCP_PROJECT_ID environment variable"
    echo "Example: export GCP_PROJECT_ID=your-project-id"
    read -p "Enter your GCP Project ID: " PROJECT_ID
fi

# Set the project
echo "📦 Setting GCP project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com run.googleapis.com

# Build and push the Docker image
echo "🏗️  Building Docker image..."
gcloud builds submit --tag "$IMAGE_NAME" .

# Deploy to Cloud Run
echo "🚢 Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_NAME" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY:-}"

# Get the service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format 'value(status.url)')

echo ""
echo "✅ Backend deployment complete!"
echo "📍 Service URL: $SERVICE_URL"
echo "📄 API Docs: $SERVICE_URL/docs"
echo ""
echo "💡 Next steps:"
echo "   1. Test the API: curl $SERVICE_URL/health"
echo "   2. Set OPENAI_API_KEY: gcloud run services update $SERVICE_NAME --set-env-vars OPENAI_API_KEY=your-key"
echo "   3. Deploy frontend with: NEXT_PUBLIC_API_BASE_URL=$SERVICE_URL ./deploy-frontend.sh"
echo ""
