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

# Step 1: install dependencies only (cacheable layer — rebuilt only when
# pyproject.toml or uv.lock change, not when src/ changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project \
    --allow-insecure-host pypi.org \
    --allow-insecure-host files.pythonhosted.org

# Pre-install @playwright/mcp globally so npx finds it without a network fetch.
RUN npm install -g @playwright/mcp

# Optional: install Chromium for local Docker testing (without Browserbase).
# Fly.io deploy uses Browserbase (QA_BROWSER=browserbase in fly.toml).
# Usage: docker build --build-arg INSTALL_CHROMIUM=true -t qa-agent-local .
ARG INSTALL_CHROMIUM=false
RUN if [ "$INSTALL_CHROMIUM" = "true" ]; then \
    npx playwright install --with-deps chromium; \
    fi

# Step 2: copy source, then install the local package into the existing venv.
COPY src/ ./src/
RUN uv sync --no-dev \
    --allow-insecure-host pypi.org \
    --allow-insecure-host files.pythonhosted.org

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    NO_UPDATE_NOTIFIER=1

# Reports and state live on a mounted Fly volume (see fly.toml [mounts]).
RUN mkdir -p reports

EXPOSE 8080

CMD ["uvicorn", "qa_agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
