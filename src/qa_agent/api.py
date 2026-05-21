"""
FastAPI HTTP wrapper for qa-agent.

Endpoints:
  POST /products                              — create a product record
  GET  /products                              — list all products
  GET  /products/{id}                         — get product
  POST /products/{id}/analyze                 — run analyst + save specs to DB (202 Accepted)
  GET  /products/{id}/analyze/{task_id}       — poll analysis status
  GET  /products/{id}/analyze/{task_id}/logs  — cursor-based log stream (?since=N)
  GET  /products/{id}/specs                   — list specs for a product
  GET  /products/{id}/specs/{filename}        — get spec content
  PUT  /products/{id}/specs/{filename}        — create / update spec content
  DELETE /products/{id}/specs/{filename}      — delete spec
  POST /products/{id}/specs/{filename}/approve — set approved flag

  POST /runs                     — create a run; accepts spec_dir or product_id (202 Accepted)
  GET  /runs                     — list all runs (in-memory + disk)
  GET  /runs/{run_id}            — poll run status
  GET  /runs/{run_id}/logs       — cursor-based log stream (?since=N)
  POST /runs/{run_id}/cancel     — cancel a pending/running run (202; 409 if already terminal)
  GET  /runs/{run_id}/report     — return report.json
  GET  /health                   — liveness probe (no auth required)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Body, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from qa_agent.agent import preflight_check, run_requirement
from qa_agent.analyst import run_analysis
from qa_agent.log_sink import BufferSink
from qa_agent.auth import CurrentUser, get_current_user
from qa_agent.llm import LLMConfig
from qa_agent.reporter import write_run
from qa_agent.specs import load_spec
from qa_agent.state import StateStore
from qa_agent.db import init as db_init, close as db_close
from qa_agent.db import jobs as db_jobs
from qa_agent.db import products as db_products
from qa_agent.db import specs as db_specs
from qa_agent.db import issues as db_issues
from qa_agent.db import quota as db_quota
from qa_agent.issues import BufferingIssueSink

def _rate_limit_key(request: Request) -> str:
    """Rate-limit key: user UUID from JWT when available, fallback to client IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        secret = os.getenv("SUPABASE_JWT_SECRET", "")
        if secret:
            try:
                payload = pyjwt.decode(
                    auth[7:], secret, algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                sub = payload.get("sub", "")
                if sub:
                    return sub
            except Exception:
                pass
    return get_remote_address(request)


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Please try again later."},
    )


limiter = Limiter(key_func=_rate_limit_key)

app = FastAPI(title="qa-agent", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

_DEFAULT_REPORTS_DIR = Path("reports")
_FRONTEND_DIR = Path(__file__).parent / "frontend"

# ---------------------------------------------------------------------------
# Tier limits
# ---------------------------------------------------------------------------

_TIER_LIMITS: dict[str, dict] = {
    "free":    {"runs": 5,  "scans": 2,  "scenarios": 15, "models": ["claude-haiku-4-5-20251001"]},
    "beta":    {"runs": 10, "scans": 3,  "scenarios": 20, "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]},
    "starter": {"runs": 20, "scans": 5,  "scenarios": 30, "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]},
    "pro":     {"runs": 50, "scans": 10, "scenarios": 75, "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"]},
}
_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "anghel.contiu@gmail.com")


async def _send_quota_email(user_email: str, event_type: str) -> None:
    """Send a quota-limit notification via Resend. No-op if RESEND_API_KEY is unset."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return
    import httpx
    limit_label = "test runs" if event_type == "run_blocked" else "site scans"
    user_html = (
        f"<p>Hi,</p>"
        f"<p>You've used all your <strong>{limit_label}</strong> for this month on Steadra.</p>"
        f"<p>You're clearly getting value — we'd love to hear what you think. "
        f"Reply to this email and we'll unlock more access for you.</p>"
        f"<p>Paid plans with higher limits are coming soon.</p>"
        f"<p>— Anghel, Steadra</p>"
    )
    admin_html = (
        f"<p><strong>{user_email}</strong> hit their <strong>{event_type}</strong> quota.</p>"
        f"<p>Reach out — this is a hot lead.</p>"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        for to, subject, html in [
            (user_email, "You've hit your Steadra beta limit", user_html),
            (_ADMIN_EMAIL, f"[Steadra] quota hit: {user_email}", admin_html),
        ]:
            try:
                await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"from": "Steadra <noreply@steadra.dev>", "to": [to], "subject": subject, "html": html},
                )
            except Exception:
                pass

_SPA_ROUTE_PREFIXES = ("/products", "/runs", "/login")

@app.middleware("http")
async def _www_redirect_middleware(request: Request, call_next: Any) -> Any:
    host = request.headers.get("host", "")
    if host.startswith("www."):
        url = request.url.replace(netloc=host[4:])
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=str(url), status_code=301)
    return await call_next(request)


@app.middleware("http")
async def _spa_html_middleware(request: Request, call_next: Any) -> Any:
    """Serve index.html for browser navigations to React Router paths.

    Hard-refreshing /runs or /products would otherwise hit the FastAPI JSON
    endpoints (same paths) before the React app loads. Browser navigations
    send Accept: text/html explicitly; fetch() calls send Accept: */* which
    does not contain the literal string 'text/html'.
    """
    accept = request.headers.get("accept", "")
    path = request.url.path
    is_browser_nav = request.method == "GET" and "text/html" in accept
    is_spa_route = path == "/" or any(
        path == p or path.startswith(p + "/") for p in _SPA_ROUTE_PREFIXES
    )
    if is_browser_nav and is_spa_route and _FRONTEND_DIR.exists():
        return FileResponse(_FRONTEND_DIR / "index.html")
    return await call_next(request)
_STATE_DB = Path("reports/.state/runs.db")

_assets_dir = _FRONTEND_DIR / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

# In-memory registry: run_id → status dict.
# Dual-written to Postgres when DATABASE_URL is set.
_runs: dict[str, dict] = {}

# Task registry: run_id → asyncio.Task (for cancellation).
_tasks: dict[str, asyncio.Task] = {}

# In-memory registry for analysis tasks (not persisted to DB yet).
_analyses: dict[str, dict] = {}


async def _ensure_dev_user() -> None:
    """Insert the dev user row when running without SUPABASE_JWT_SECRET (local dev only)."""
    from qa_agent.auth import _DEV_USER_ID, _DEV_USER_EMAIL  # type: ignore[attr-defined]
    from qa_agent.db import get_pool
    if os.getenv("SUPABASE_JWT_SECRET"):
        return
    pool = get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (id, email) VALUES ($1::uuid, $2)
            ON CONFLICT (id) DO NOTHING
            """,
            _DEV_USER_ID, _DEV_USER_EMAIL,
        )


@app.on_event("startup")
async def _startup() -> None:
    await db_init()
    await _ensure_dev_user()
    await db_jobs.mark_interrupted()
    for status_file in _DEFAULT_REPORTS_DIR.glob("run-*/run_status.json"):
        try:
            state = json.loads(status_file.read_text())
            if state.get("status") in ("running", "pending"):
                state.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": "Interrupted by server restart",
                })
                status_file.write_text(json.dumps(state, indent=2))
        except Exception:
            pass


@app.on_event("shutdown")
async def _shutdown() -> None:
    await db_close()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProductRequest(BaseModel):
    name: str
    url: str
    description: str | None = None


class AnalyzeRequest(BaseModel):
    url: str
    description: str
    spec_prefix: str = "SC"
    pages: list[str] | None = None
    max_scenarios: int | None = None


class SpecUpdateRequest(BaseModel):
    content: str


class ApproveRequest(BaseModel):
    approved: bool = True


class RunRequest(BaseModel):
    spec_dir: str | None = None
    product_id: str | None = None
    env: str | None = None
    output: str = "reports"
    only_failing: bool = False
    executor_provider: str | None = None
    executor_model: str | None = None
    max_scenarios: int | None = None  # overrides QA_MAX_SCENARIOS


class RunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errored: int


class RunStatus(BaseModel):
    run_id: str
    status: Literal["pending", "running", "done", "failed", "cancelled"]
    spec_dir: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    summary: RunSummary | None = None
    report_path: str | None = None
    error: str | None = None

    model_config = {"extra": "ignore"}


def _scenario_cap() -> int | None:
    """Return QA_MAX_SCENARIOS env value, or None if unset/zero."""
    raw = os.environ.get("QA_MAX_SCENARIOS", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------

async def _execute_job(run_id: str, req: RunRequest, output_dir: Path) -> None:
    state = _runs[run_id]
    state["logs"] = []
    sink = BufferSink(state["logs"])
    state["status"] = "running"
    _write_status_file(output_dir, run_id, state)

    try:
        if req.product_id:
            files = await db_specs.get_files_dict(req.product_id)
            if not files:
                _mark_failed(run_id, state, output_dir, f"No specs found for product {req.product_id}")
                return
            temp_dir = output_dir / f"run-{run_id}" / ".specs"
            temp_dir.mkdir(parents=True, exist_ok=True)
            for filename, content in files.items():
                (temp_dir / filename).write_text(content, encoding="utf-8")
            bundle = load_spec(temp_dir)
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            bundle = load_spec(Path(req.spec_dir))
        url = bundle.config.get_url(req.env)
    except (FileNotFoundError, ValueError) as e:
        _mark_failed(run_id, state, output_dir, str(e))
        return

    llm = LLMConfig.from_env(role="executor")
    if req.executor_provider:
        llm.provider = req.executor_provider
    if req.executor_model:
        llm.model = req.executor_model

    requirements = bundle.requirements

    spec_key = req.spec_dir or f"product:{req.product_id}"
    if req.only_failing:
        store = StateStore(_STATE_DB)
        prev_run_id = store.last_run_id(spec_key)
        if prev_run_id:
            failing = store.failing_ids(prev_run_id)
            requirements = [r for r in requirements if r.id in failing]
        store.close()

    cap = req.max_scenarios or _scenario_cap()
    if cap and len(requirements) > cap:
        requirements = requirements[:cap]
        state["capped_at"] = cap

    try:
        await preflight_check()
    except RuntimeError as e:
        _mark_failed(run_id, state, output_dir, f"Preflight failed: {e}")
        return

    scenario_delay = int(os.environ.get("QA_SCENARIO_DELAY", "3"))

    n = len(requirements)
    results: list[dict] = []
    try:
        for i, req_item in enumerate(requirements):
            if i > 0 and scenario_delay > 0:
                await asyncio.sleep(scenario_delay)
            req_dict = req_item.to_executor_dict()
            sink.emit(f"[{i+1}/{n}] {req_dict['id']} — {req_dict.get('title', '')[:60]}")
            result = await run_requirement(
                req_dict, url, llm, context=bundle.config.context, sink=sink
            )
            results.append(result)
            icon = "✓" if result.get("status") == "pass" else "✗"
            sink.emit(f"[{i+1}/{n}] {icon} {result.get('status')} ({result.get('duration_s', 0):.1f}s)")
    except asyncio.CancelledError:
        sink.emit(f"Cancelled after {len(results)}/{n} scenarios")
        state.update({
            "status": "cancelled",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": f"Cancelled after {len(results)} of {n} scenarios",
        })
        _write_status_file(output_dir, run_id, state)
        raise
    except Exception as e:
        _mark_failed(run_id, state, output_dir, f"Execution error: {e}")
        return

    run_dir = write_run(results, bundle, url, output_dir, req.env, run_id=run_id)

    store = StateStore(_STATE_DB)
    store.save_run(
        run_id=run_id,
        spec_path=spec_key,
        url=url,
        environment=req.env or bundle.config.default_environment,
        started_at=run_id,
        results=results,
    )
    store.close()

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed_count = sum(1 for r in results if r.get("status") == "fail")
    errored = sum(1 for r in results if r.get("status") == "error")
    sink.emit(f"Done: {passed} passed, {failed_count} failed, {errored} errored")

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed_count,
        "errored": errored,
    }
    state.update({
        "status": "done",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "report_path": str(run_dir / "report.json"),
    })
    _write_status_file(output_dir, run_id, state)
    await db_jobs.update(run_id, status="done",
        completed_at=datetime.now(timezone.utc),
        summary=summary,
        report_path=str(run_dir / "report.json"))


def _mark_failed(run_id: str, state: dict, output_dir: Path, error: str) -> None:
    state.update({
        "status": "failed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    })
    _write_status_file(output_dir, run_id, state)
    asyncio.ensure_future(db_jobs.update(run_id, status="failed",
        completed_at=datetime.now(timezone.utc), error=error))


def _write_status_file(output_dir: Path, run_id: str, state: dict) -> None:
    run_dir = output_dir / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_status.json").write_text(json.dumps(state, indent=2))


def _assert_run_owner(state: dict, user: CurrentUser, run_id: str) -> None:
    """Raise HTTP 404 if the run belongs to a different user.

    Returns 404 (not 403) to avoid leaking existence of other users' runs.
    Skips the check for legacy state files that pre-date auth (no user_id field).
    """
    owner = state.get("user_id")
    if owner and owner != user.user_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/me/quota")
async def get_my_quota(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return tier, limits, and current-month usage for the authenticated user."""
    tier = await db_quota.get_tier(user.user_id)
    limits = _TIER_LIMITS.get(tier, _TIER_LIMITS["free"])
    runs_used = await db_quota.count_runs_this_month(user.user_id)
    scans_used = await db_quota.count_scans_this_month(user.user_id)
    return {
        "tier": tier,
        "limits": {
            "runs_per_month": limits["runs"],
            "scans_per_month": limits["scans"],
            "scenarios_per_run": limits["scenarios"],
        },
        "usage": {
            "runs_this_month": runs_used,
            "scans_this_month": scans_used,
        },
        "models_allowed": limits["models"],
    }


@app.get("/spec-dirs")
async def list_spec_dirs(
    user: CurrentUser = Depends(get_current_user),
) -> list[str]:
    """List subdirectories of the local specs/ folder, sorted alphabetically."""
    specs_root = Path("specs")
    if not specs_root.is_dir():
        return []
    return sorted(p.name for p in specs_root.iterdir() if p.is_dir())


@app.post("/runs", response_model=RunStatus, status_code=202)
@limiter.limit("10/hour")
async def create_run(
    request: Request,
    req: RunRequest,
    user: CurrentUser = Depends(get_current_user),
) -> RunStatus:
    """Start a QA run. Returns immediately with run_id; poll GET /runs/{run_id} for status."""
    if not req.spec_dir and not req.product_id:
        raise HTTPException(status_code=422, detail="Either spec_dir or product_id must be provided")

    # ── Quota enforcement ────────────────────────────────────────────────────
    tier = await db_quota.get_tier(user.user_id)
    limits = _TIER_LIMITS.get(tier, _TIER_LIMITS["free"])

    # Block disallowed models
    if req.executor_model and req.executor_model not in limits["models"]:
        raise HTTPException(
            status_code=403,
            detail=f"Model '{req.executor_model}' is not available on the {tier} plan.",
        )

    # Enforce scenarios/run cap
    scenarios_cap = limits["scenarios"]
    if req.max_scenarios is None or req.max_scenarios > scenarios_cap:
        req = req.model_copy(update={"max_scenarios": scenarios_cap})

    # Enforce monthly run limit
    runs_used = await db_quota.count_runs_this_month(user.user_id)
    if runs_used >= limits["runs"]:
        first_block = not await db_quota.already_notified_this_month(user.user_id, "run_blocked")
        await db_quota.log_quota_event(user.user_id, "run_blocked")
        if first_block:
            asyncio.ensure_future(_send_quota_email(user.email, "run_blocked"))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exceeded",
                "type": "run_blocked",
                "used": runs_used,
                "limit": limits["runs"],
                "tier": tier,
            },
        )

    if req.product_id:
        product = await db_products.get(req.product_id, user_id=user.user_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product '{req.product_id}' not found")
        raw_slug = product["name"].lower()
    else:
        raw_slug = Path(req.spec_dir).name.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', raw_slug).strip('-') or "run"
    run_id = f"{slug}-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
    output_dir = Path(req.output)
    spec_key = req.spec_dir or f"product:{req.product_id}"

    state: dict = {
        "run_id": run_id,
        "status": "pending",
        "spec_dir": spec_key,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.user_id,
    }
    _runs[run_id] = state
    _write_status_file(output_dir, run_id, state)
    await db_jobs.create(run_id, spec_key,
                         user_id=user.user_id,
                         executor_model=req.executor_model,
                         max_scenarios=req.max_scenarios)

    task = asyncio.create_task(_execute_job(run_id, req, output_dir))
    _tasks[run_id] = task
    return RunStatus(**state)


@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(
    run_id: str,
    output: str = "reports",
    user: CurrentUser = Depends(get_current_user),
) -> RunStatus:
    """Poll run status. Falls back to disk for runs from previous server sessions."""
    if run_id in _runs:
        state = _runs[run_id]
        _assert_run_owner(state, user, run_id)
        return RunStatus(**state)

    status_file = Path(output) / f"run-{run_id}" / "run_status.json"
    if status_file.exists():
        state = json.loads(status_file.read_text())
        _assert_run_owner(state, user, run_id)
        return RunStatus(**state)

    raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")


@app.post("/runs/{run_id}/cancel", response_model=RunStatus, status_code=202)
async def cancel_run(
    run_id: str,
    output: str = "reports",
    user: CurrentUser = Depends(get_current_user),
) -> RunStatus:
    """Cancel a pending or running run.

    Returns 202 Accepted when cancellation is requested (async — task stops at the
    next await point, between scenarios). Returns 409 Conflict if the run is already
    in a terminal state (done/failed/cancelled).
    """
    task = _tasks.get(run_id)
    state = _runs.get(run_id)

    if state is None:
        status_file = Path(output) / f"run-{run_id}" / "run_status.json"
        if not status_file.exists():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        state = json.loads(status_file.read_text())

    _assert_run_owner(state, user, run_id)

    if state["status"] in ("done", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' is already {state['status']} — cannot cancel",
        )

    if task is None or task.done():
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' has no active task — it was likely interrupted by a server restart",
        )

    task.cancel()
    return RunStatus(**state)


@app.get("/runs", response_model=list[RunStatus])
async def list_runs(
    output: str = "reports",
    user: CurrentUser = Depends(get_current_user),
) -> list[RunStatus]:
    """List all runs for the current user (in-memory + persisted on disk), newest first."""
    runs: list[RunStatus] = []
    seen: set[str] = set()

    for run_id, state in _runs.items():
        owner = state.get("user_id")
        if owner is None or owner == user.user_id:
            runs.append(RunStatus(**state))
            seen.add(run_id)

    output_dir = Path(output)
    if output_dir.exists():
        for status_file in sorted(output_dir.glob("run-*/run_status.json"), reverse=True):
            rid = status_file.parent.name.removeprefix("run-")
            if rid not in seen:
                try:
                    state = json.loads(status_file.read_text())
                    owner = state.get("user_id")
                    if owner is None or owner == user.user_id:
                        runs.append(RunStatus(**state))
                except Exception:
                    pass

    return sorted(runs, key=lambda r: r.run_id, reverse=True)


@app.get("/runs/{run_id}/report")
async def get_report(
    run_id: str,
    output: str = "reports",
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return the report.json for a completed run."""
    # Ownership check via run status file
    status_file = Path(output) / f"run-{run_id}" / "run_status.json"
    if status_file.exists():
        state = json.loads(status_file.read_text())
        _assert_run_owner(state, user, run_id)

    report_file = Path(output) / f"run-{run_id}" / "report.json"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Report for run '{run_id}' not found")
    return json.loads(report_file.read_text())


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.post("/products", status_code=201)
async def create_product(
    req: ProductRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    product_id = await db_products.create(req.name, req.url, req.description, user_id=user.user_id)
    return await db_products.get(product_id)


@app.get("/products")
async def list_products(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return await db_products.list_all(user_id=user.user_id)


@app.get("/products/{product_id}")
async def get_product(
    product_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    product = await db_products.get(product_id, user_id=user.user_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    return product


# ---------------------------------------------------------------------------
# Analysis (analyst runs in background, saves specs to DB)
# ---------------------------------------------------------------------------

async def _run_analysis_task(task_id: str, product_id: str, req: AnalyzeRequest) -> None:
    state = _analyses[task_id]
    state["logs"] = []
    sink = BufferSink(state["logs"])
    issues_sink = BufferingIssueSink()
    try:
        output_dir = _DEFAULT_REPORTS_DIR / "analyses" / task_id
        result = await run_analysis(
            url=req.url,
            description=req.description,
            output_dir=output_dir,
            spec_prefix=req.spec_prefix,
            pages=req.pages,
            product_id=product_id,
            max_scenarios_per_file=req.max_scenarios,
            sink=sink,
            issues_sink=issues_sink,
        )
        state.update({
            "status": "done",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "files_written": result["files_written"],
            "file_count": result["file_count"],
            "summary": result["summary"],
            "cost_usd": result.get("cost_usd"),
            "issues_count": result.get("issues_count", 0),
        })
        asyncio.ensure_future(db_jobs.update(task_id, status="done",
            completed_at=datetime.now(timezone.utc)))
    except Exception as e:
        state.update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })
        asyncio.ensure_future(db_jobs.update(task_id, status="failed",
            completed_at=datetime.now(timezone.utc), error=str(e)))


@app.post("/products/{product_id}/analyze", status_code=202)
@limiter.limit("3/hour")
async def analyze_product(
    request: Request,
    product_id: str,
    req: AnalyzeRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Trigger analyst for a product. Saves generated specs to DB. Poll with GET."""
    product = await db_products.get(product_id, user_id=user.user_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    # ── Quota enforcement ────────────────────────────────────────────────────
    tier = await db_quota.get_tier(user.user_id)
    limits = _TIER_LIMITS.get(tier, _TIER_LIMITS["free"])
    scans_used = await db_quota.count_scans_this_month(user.user_id)
    if scans_used >= limits["scans"]:
        first_block = not await db_quota.already_notified_this_month(user.user_id, "scan_blocked")
        await db_quota.log_quota_event(user.user_id, "scan_blocked")
        if first_block:
            asyncio.ensure_future(_send_quota_email(user.email, "scan_blocked"))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exceeded",
                "type": "scan_blocked",
                "used": scans_used,
                "limit": limits["scans"],
                "tier": tier,
            },
        )

    task_id = f"analyze-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
    state: dict = {
        "task_id": task_id,
        "product_id": product_id,
        "user_id": user.user_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _analyses[task_id] = state
    # Record in jobs table so monthly scan counter works
    await db_jobs.create(task_id, f"analyze:{product_id}", user_id=user.user_id)
    asyncio.create_task(_run_analysis_task(task_id, product_id, req))
    return state


@app.get("/products/{product_id}/analyze/{task_id}")
async def get_analysis_task(
    product_id: str,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    state = _analyses.get(task_id)
    if not state or state.get("product_id") != product_id:
        raise HTTPException(status_code=404, detail=f"Analysis task '{task_id}' not found")
    owner = state.get("user_id")
    if owner and owner != user.user_id:
        raise HTTPException(status_code=404, detail=f"Analysis task '{task_id}' not found")
    return state


@app.get("/products/{product_id}/analyze/{task_id}/logs")
async def get_analysis_logs(
    product_id: str,
    task_id: str,
    since: int = 0,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Cursor-based log stream for an analysis task. Returns events[since:] + next cursor."""
    state = _analyses.get(task_id)
    if not state or state.get("product_id") != product_id:
        raise HTTPException(status_code=404, detail=f"Analysis task '{task_id}' not found")
    owner = state.get("user_id")
    if owner and owner != user.user_id:
        raise HTTPException(status_code=404, detail=f"Analysis task '{task_id}' not found")
    logs: list = state.get("logs", [])
    return {"events": logs[since:], "next": len(logs)}


@app.get("/runs/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    since: int = 0,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Cursor-based log stream for an executor run. Returns events[since:] + next cursor."""
    state = _runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    _assert_run_owner(state, user, run_id)
    logs: list = state.get("logs", [])
    return {"events": logs[since:], "next": len(logs)}


# ---------------------------------------------------------------------------
# Specs CRUD
# ---------------------------------------------------------------------------

async def _get_owned_product(product_id: str, user: CurrentUser) -> dict:
    """Return product dict or raise 404. Implicitly enforces ownership."""
    product = await db_products.get(product_id, user_id=user.user_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    return product


@app.get("/products/{product_id}/specs")
async def list_specs(
    product_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    await _get_owned_product(product_id, user)
    return await db_specs.list_by_product(product_id)


@app.get("/products/{product_id}/specs/{filename:path}")
async def get_spec(
    product_id: str,
    filename: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    await _get_owned_product(product_id, user)
    spec = await db_specs.get_by_filename(product_id, filename)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Spec '{filename}' not found")
    return spec


@app.put("/products/{product_id}/specs/{filename:path}", status_code=200)
async def upsert_spec(
    product_id: str,
    filename: str,
    req: SpecUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    await _get_owned_product(product_id, user)
    await db_specs.upsert(product_id, filename, req.content)
    return await db_specs.get_by_filename(product_id, filename)


@app.delete("/products/{product_id}/specs/{filename:path}", status_code=204)
async def delete_spec(
    product_id: str,
    filename: str,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    await _get_owned_product(product_id, user)
    deleted = await db_specs.delete(product_id, filename)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Spec '{filename}' not found")


@app.post("/products/{product_id}/specs/{filename:path}/approve")
async def approve_spec(
    product_id: str,
    filename: str,
    req: ApproveRequest = Body(default=ApproveRequest()),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    await _get_owned_product(product_id, user)
    updated = await db_specs.set_approved(product_id, filename, req.approved)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Spec '{filename}' not found")
    return await db_specs.get_by_filename(product_id, filename)


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

class IssueStatusUpdate(BaseModel):
    status: Literal["open", "acknowledged", "wont_fix", "resolved"]


@app.get("/products/{product_id}/issues")
async def list_issues(
    product_id: str,
    status: str | None = None,
    severity: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List issues found during analyst crawls for a product."""
    await _get_owned_product(product_id, user)
    return await db_issues.list_by_product(product_id, status=status, severity=severity)


@app.get("/products/{product_id}/issues/summary")
async def get_issues_summary(
    product_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return count of open issues by severity."""
    await _get_owned_product(product_id, user)
    return await db_issues.summary(product_id)


@app.patch("/products/{product_id}/issues/{issue_id}")
async def update_issue_status(
    product_id: str,
    issue_id: str,
    req: IssueStatusUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update issue status (acknowledge, mark won't-fix, resolve)."""
    await _get_owned_product(product_id, user)
    updated = await db_issues.update_status(product_id, issue_id, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found")
    issues = await db_issues.list_by_product(product_id)
    for issue in issues:
        if issue["id"] == issue_id:
            return issue
    raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Waitlist
# ---------------------------------------------------------------------------

class _WaitlistEntry(BaseModel):
    email: str

@app.post("/waitlist", status_code=201)
@limiter.limit("5/minute")
async def join_waitlist(request: Request, entry: _WaitlistEntry) -> dict:
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", entry.email):
        raise HTTPException(status_code=422, detail="Invalid email")

    waitlist_file = _DEFAULT_REPORTS_DIR / ".state" / "waitlist.json"
    waitlist_file.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    if waitlist_file.exists():
        try:
            entries = json.loads(waitlist_file.read_text())
        except Exception:
            entries = []

    if any(e.get("email") == entry.email for e in entries):
        raise HTTPException(status_code=409, detail="Already on the waitlist")

    entries.append({"email": entry.email, "joined_at": datetime.now(timezone.utc).isoformat()})
    waitlist_file.write_text(json.dumps(entries, indent=2))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.get("/auth/config")
async def auth_config() -> dict:
    """Return public Supabase config needed by the frontend JS SDK. No auth required."""
    return {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    }


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    """SPA fallback — serve index.html for all non-API routes so React Router works."""
    return FileResponse(_FRONTEND_DIR / "index.html")
