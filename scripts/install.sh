#!/bin/bash
set -e

echo "=== QA Agent — install ==="

# Python deps
echo "[1/2] Installing Python dependencies..."
uv sync

# Playwright browsers (used by @playwright/mcp Node package)
echo "[2/2] Installing Playwright Chromium..."
npx playwright install chromium

echo ""
echo "Done. Copy .env.example to .env and set ANTHROPIC_API_KEY."
echo "Then run: uv run python -m qa_agent.smoke"
