# Backend (FastAPI) Dockerfile for Cloud Run
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run sets PORT environment variable, but we'll default to 8000
ENV PORT=8000

# Expose port (informational)
EXPOSE 8000

# Run the application
# Cloud Run provides PORT env var, so we use it if available
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
