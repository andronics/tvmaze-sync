FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package configuration first for better caching
COPY pyproject.toml README.md ./

# Copy application source
COPY src/ ./src/

# Install package and dependencies
RUN pip install --no-cache-dir .

# Create non-root user for security
RUN useradd -m -u 1000 tvmaze && \
    chown -R tvmaze:tvmaze /app

# Create volume mount points
VOLUME ["/data", "/config"]

# Expose HTTP server port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Switch to non-root user
USER tvmaze

# Set default environment variables
ENV CONFIG_PATH=/config/config.yaml \
    STORAGE_PATH=/data \
    PYTHONUNBUFFERED=1

# Run application
ENTRYPOINT ["tvmaze-sync"]
