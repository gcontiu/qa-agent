FROM python:3.12-slim

# Node 20 — required for npx @playwright/mcp and React build
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/*

# uv — fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Step 1: install Python dependencies only (cacheable — rebuilt when pyproject.toml or uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project \
    --allow-insecure-host pypi.org \
    --allow-insecure-host files.pythonhosted.org

# Pre-install @playwright/mcp globally so npx finds it without a network fetch.
RUN npm install -g @playwright/mcp@0.0.75

# Install Chromium for local Playwright (used in Fly.io deploy and local Docker).
# Set INSTALL_CHROMIUM=false to skip if you want a smaller image and use
# Browserbase instead (requires QA_BROWSERBASE_API_KEY + QA_BROWSERBASE_PROJECT_ID).
ARG INSTALL_CHROMIUM=true
RUN if [ "$INSTALL_CHROMIUM" = "true" ]; then \
    npx playwright install --with-deps chromium; \
    fi

# Step 2: build React frontend (Node is already present above).
# Cached when frontend/package-lock.json hasn't changed.
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# Step 3: copy Python source and built frontend into package, then install.
COPY src/ ./src/
RUN rm -rf src/qa_agent/frontend && \
    mkdir -p src/qa_agent/frontend && \
    cp -r frontend/dist/. src/qa_agent/frontend/

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
