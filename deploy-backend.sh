#!/bin/bash

# Cloud Run Backend (FastAPI) Deployment Script
# Usage: ./deploy-backend.sh

set -e

echo "🚀 Starting backend deployment to Cloud Run..."

# Load environment variables from .env file if it exists
if [ -f .env ]; then
  echo "📄 Loading environment variables from .env file..."
  export $(grep -v '^#' .env | xargs)
fi

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE_NAME="${BACKEND_SERVICE_NAME:-cardemon-backend}"
REPOSITORY_NAME="${ARTIFACT_REGISTRY_REPO:-cardemon}"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY_NAME}/${SERVICE_NAME}"

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

# Validate required environment variables
echo "🔍 Validating required environment variables..."
MISSING_VARS=()

if [ -z "$MONGODB_URI" ]; then
  MISSING_VARS+=("MONGODB_URI")
fi

if [ -z "$OPENAI_API_KEY" ]; then
  MISSING_VARS+=("OPENAI_API_KEY")
fi

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
  echo "❌ Missing required environment variables:"
  for var in "${MISSING_VARS[@]}"; do
    echo "   - $var"
  done
  echo ""
  echo "💡 Please set these variables in your .env file or export them:"
  echo "   export MONGODB_URI='your-mongodb-connection-string'"
  echo "   export OPENAI_API_KEY='your-openai-api-key'"
  exit 1
fi

echo "✅ All required environment variables are set"

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
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY:-},MONGODB_URI=${MONGODB_URI:-},MONGODB_DATABASE=${MONGODB_DATABASE:-cardemon},MONGODB_COLLECTION_CARDS=${MONGODB_COLLECTION_CARDS:-cards}"

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
