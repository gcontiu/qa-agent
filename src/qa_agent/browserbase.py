"""
Browserbase cloud browser session management.

Creates a remote browser session before Playwright MCP starts, and deletes it
afterwards. Playwright MCP connects via --cdp-endpoint instead of launching a
local browser. Each run_requirement call gets its own isolated session.

Required env vars:
  QA_BROWSERBASE_API_KEY     — Browserbase API key
  QA_BROWSERBASE_PROJECT_ID  — Browserbase project ID

Optional:
  QA_BROWSERBASE_REGION      — cloud region (default: let Browserbase choose)
  QA_BROWSERBASE_TIMEOUT     — session timeout in seconds (default: 300)
"""
import json
import os
import urllib.error
import urllib.request

_API_BASE = "https://api.browserbase.com/v1"


def is_configured() -> bool:
    """Return True if the minimum env vars needed to use Browserbase are set."""
    return bool(os.getenv("QA_BROWSERBASE_API_KEY") and os.getenv("QA_BROWSERBASE_PROJECT_ID"))


def create_session() -> tuple[str, str]:
    """Create a Browserbase session and return (session_id, cdp_url).

    cdp_url is the WebSocket CDP endpoint to pass to Playwright MCP via
    --cdp-endpoint. Raises RuntimeError on API failure.
    """
    api_key = os.environ["QA_BROWSERBASE_API_KEY"]
    project_id = os.environ["QA_BROWSERBASE_PROJECT_ID"]
    timeout = int(os.getenv("QA_BROWSERBASE_TIMEOUT", "300"))

    body: dict = {"projectId": project_id, "timeout": timeout}
    region = os.getenv("QA_BROWSERBASE_REGION", "").strip()
    if region:
        body["region"] = region

    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_API_BASE}/sessions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-BB-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"Browserbase session creation failed ({e.code}): {body_text}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Browserbase API unreachable: {e.reason}") from e

    session_id = data["id"]
    # Use the connectUrl returned by the API — it is region-specific and
    # contains a signed token. Never construct this URL manually.
    cdp_url = data["connectUrl"]
    return session_id, cdp_url


def delete_session(session_id: str) -> None:
    """Delete a Browserbase session. Best-effort — swallows all errors.

    Called in a finally block so test results are never lost due to cleanup
    failures.
    """
    api_key = os.getenv("QA_BROWSERBASE_API_KEY", "")
    req = urllib.request.Request(
        f"{_API_BASE}/sessions/{session_id}",
        headers={"X-BB-API-Key": api_key},
        method="DELETE",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass
