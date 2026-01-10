# Backend Dockerfile
FROM python:3.13-slim

# Install system dependencies
# libaio1 is often needed for Oracle, even in Thin mode for some scenarios, or just good to have.
# magic/libmagic for python-magic (if we revert to it), but we use puremagic now.
# curl/wget for healthchecks.
RUN apt-get update && apt-get install -y \
  build-essential \
  libaio1t64 \
  curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for caching
# Copy requirements first for caching
COPY requirements-prod.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create unprivileged user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
