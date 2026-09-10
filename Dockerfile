# ==============================================================================
# Stage 1: Builder Stage
# ==============================================================================
FROM python:3.13-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install production dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    sse-starlette \
    redis \
    fakeredis \
    httpx \
    arq \
    langgraph \
    langchain-core \
    ddgs \
    pydantic \
    pydantic-settings \
    pytest \
    pytest-asyncio

# ==============================================================================
# Stage 2: Production Runner Stage (Non-Root Execution)
# ==============================================================================
FROM python:3.13-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Create a dedicated non-root user & group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy virtual environment and application files with non-root ownership
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --chown=appuser:appgroup . /app

# Switch to non-root user
USER appuser:appgroup

EXPOSE 8000

# Default command (Web Gateway)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
