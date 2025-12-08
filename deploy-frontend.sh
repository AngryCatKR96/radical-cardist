#!/bin/bash

# Cloud Run Frontend (Next.js) Deployment Script
# Usage: ./deploy-frontend.sh

set -e

echo "🚀 Starting frontend deployment to Cloud Run..."

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE_NAME="${FRONTEND_SERVICE_NAME:-cardemon-frontend}"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Backend URL (required)
BACKEND_URL="${NEXT_PUBLIC_API_BASE_URL:-}"

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

# Check if backend URL is set
if [ -z "$BACKEND_URL" ]; then
    echo "⚠️  Warning: Backend URL not set"
    read -p "Enter your backend URL (e.g., https://backend-xxx.run.app): " BACKEND_URL
fi

# Set the project
echo "📦 Setting GCP project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com run.googleapis.com

# Build and push the Docker image
echo "🏗️  Building Docker image with backend URL: $BACKEND_URL"
gcloud builds submit \
  --config ./frontend/cloudbuild.yaml \
  --substitutions _API_BASE_URL="$BACKEND_URL",_IMAGE_NAME="$IMAGE_NAME" \
  .

# Deploy to Cloud Run
echo "🚢 Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_NAME" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60 \
  --max-instances 10 \
  --set-env-vars "NEXT_PUBLIC_API_BASE_URL=$BACKEND_URL"

# Get the service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format 'value(status.url)')

echo ""
echo "✅ Frontend deployment complete!"
echo "📍 Service URL: $SERVICE_URL"
echo ""
echo "💡 Your app is now live!"
echo "   Frontend: $SERVICE_URL"
echo "   Backend: $BACKEND_URL"
echo ""
