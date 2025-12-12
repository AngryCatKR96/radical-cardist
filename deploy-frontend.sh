#!/bin/bash

# Cloud Run Frontend (Next.js) Deployment Script
# Usage: ./deploy-frontend.sh

set -e

echo "🚀 Starting frontend deployment to Cloud Run..."

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE_NAME="${FRONTEND_SERVICE_NAME:-cardemon-frontend}"
REPOSITORY_NAME="${ARTIFACT_REGISTRY_REPO:-cardemon}"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY_NAME}/${SERVICE_NAME}"

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
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com

# Create Artifact Registry repository if it doesn't exist
echo "📦 Checking Artifact Registry repository..."
if ! gcloud artifacts repositories describe "$REPOSITORY_NAME" --location="$REGION" &> /dev/null; then
  echo "Creating Artifact Registry repository: $REPOSITORY_NAME"
  gcloud artifacts repositories create "$REPOSITORY_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Docker repository for Cardemon services"
else
  echo "Repository $REPOSITORY_NAME already exists"
fi

# Configure Cloud Build permissions for Artifact Registry
echo "🔐 Configuring Cloud Build permissions..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant Artifact Registry Writer role to Cloud Build service account
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/artifactregistry.writer" \
  --condition=None \
  --no-user-output-enabled &> /dev/null || true

echo "Cloud Build service account configured: $CLOUD_BUILD_SA"

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
