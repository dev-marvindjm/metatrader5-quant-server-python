FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# Install git for repository-based dependencies and clean up apt cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary directly from official multi-arch image (instant, zero pip timeout issues)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install python dependencies in parallel using uv
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application source code and migrations
COPY app/ ./app/
COPY alembic.ini ./

EXPOSE 8000

# Healthcheck using python standard library (zero external binary dependencies)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
