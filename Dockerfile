FROM python:3.12-slim

# Node 20 — required for npx @playwright/mcp
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/*

# uv — fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps before copying source (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Pre-install @playwright/mcp globally so npx finds it without a network fetch
# on every cold start. The version here should match what agent.py requests.
RUN npm install -g @playwright/mcp

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # Silence npm update-notifier inside the container
    NO_UPDATE_NOTIFIER=1

# Reports and state live on a mounted Fly volume (see fly.toml [mounts]).
# Create the directory so the app starts even without a volume (local Docker).
RUN mkdir -p reports

EXPOSE 8080

# Default: web process. Override CMD in fly.toml [processes] for worker.
CMD ["uvicorn", "qa_agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
