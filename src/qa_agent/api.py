"""
FastAPI HTTP wrapper for qa-agent.

Endpoints:
  POST /runs                     — create a run; returns run_id immediately (202 Accepted)
  GET  /runs                     — list all runs (in-memory + disk)
  GET  /runs/{run_id}            — poll run status
  POST /runs/{run_id}/cancel     — cancel a pending/running run (202; 409 if already terminal)
  GET  /runs/{run_id}/report     — return report.json
  GET  /health                   — liveness probe

Runs execute as asyncio tasks in the background; status is persisted to
run_dir/run_status.json so GET /runs/{run_id} survives server restarts.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from qa_agent.agent import preflight_check, run_requirement
from qa_agent.llm import LLMConfig
from qa_agent.reporter import write_run
from qa_agent.specs import load_spec
from qa_agent.state import StateStore

app = FastAPI(title="qa-agent", version="0.1.0")

_DEFAULT_REPORTS_DIR = Path("reports")
_STATE_DB = Path("reports/.state/runs.db")

# In-memory registry: run_id → status dict.
# Also persisted to run_dir/run_status.json for restartability.
_runs: dict[str, dict] = {}

# Task registry: run_id → asyncio.Task (for cancellation).
_tasks: dict[str, asyncio.Task] = {}


@app.on_event("startup")
async def _mark_interrupted_runs() -> None:
    """Mark any runs left in running/pending state as failed (interrupted by server restart)."""
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


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    spec_dir: str
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
    spec_dir: str
    started_at: str | None = None
    completed_at: str | None = None
    summary: RunSummary | None = None
    report_path: str | None = None
    error: str | None = None


def _scenario_cap() -> int | None:
    """Return QA_MAX_SCENARIOS env value, or None if unset/zero."""
    raw = os.environ.get("QA_MAX_SCENARIOS", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------

async def _execute_job(run_id: str, req: RunRequest, output_dir: Path) -> None:
    state = _runs[run_id]
    state["status"] = "running"
    _write_status_file(output_dir, run_id, state)

    try:
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

    if req.only_failing:
        store = StateStore(_STATE_DB)
        prev_run_id = store.last_run_id(req.spec_dir)
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

    results: list[dict] = []
    try:
        for req_item in requirements:
            result = await run_requirement(
                req_item.to_executor_dict(), url, llm, context=bundle.config.context
            )
            results.append(result)
    except asyncio.CancelledError:
        state.update({
            "status": "cancelled",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": f"Cancelled after {len(results)} of {len(requirements)} scenarios",
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
        spec_path=req.spec_dir,
        url=url,
        environment=req.env or bundle.config.default_environment,
        started_at=run_id,
        results=results,
    )
    store.close()

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed_count = sum(1 for r in results if r.get("status") == "fail")
    errored = sum(1 for r in results if r.get("status") == "error")

    state.update({
        "status": "done",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed_count,
            "errored": errored,
        },
        "report_path": str(run_dir / "report.json"),
    })
    _write_status_file(output_dir, run_id, state)


def _mark_failed(run_id: str, state: dict, output_dir: Path, error: str) -> None:
    state.update({
        "status": "failed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    })
    _write_status_file(output_dir, run_id, state)


def _write_status_file(output_dir: Path, run_id: str, state: dict) -> None:
    run_dir = output_dir / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_status.json").write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/runs", response_model=RunStatus, status_code=202)
async def create_run(req: RunRequest) -> RunStatus:
    """Start a QA run. Returns immediately with run_id; poll GET /runs/{run_id} for status."""
    slug = Path(req.spec_dir).name.lower()
    run_id = f"{slug}-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
    output_dir = Path(req.output)

    state: dict = {
        "run_id": run_id,
        "status": "pending",
        "spec_dir": req.spec_dir,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _runs[run_id] = state
    _write_status_file(output_dir, run_id, state)

    task = asyncio.create_task(_execute_job(run_id, req, output_dir))
    _tasks[run_id] = task
    return RunStatus(**state)


@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str, output: str = "reports") -> RunStatus:
    """Poll run status. Falls back to disk for runs from previous server sessions."""
    if run_id in _runs:
        return RunStatus(**_runs[run_id])

    status_file = Path(output) / f"run-{run_id}" / "run_status.json"
    if status_file.exists():
        return RunStatus(**json.loads(status_file.read_text()))

    raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")


@app.post("/runs/{run_id}/cancel", response_model=RunStatus, status_code=202)
async def cancel_run(run_id: str, output: str = "reports") -> RunStatus:
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

    if state["status"] in ("done", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' is already {state['status']} — cannot cancel",
        )

    if task is None or task.done():
        # Status file says running but no live task — run was interrupted (server restart)
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' has no active task — it was likely interrupted by a server restart",
        )

    task.cancel()
    return RunStatus(**state)


@app.get("/runs", response_model=list[RunStatus])
async def list_runs(output: str = "reports") -> list[RunStatus]:
    """List all runs (in-memory + persisted on disk), newest first."""
    runs: list[RunStatus] = []
    seen: set[str] = set()

    for run_id, state in _runs.items():
        runs.append(RunStatus(**state))
        seen.add(run_id)

    output_dir = Path(output)
    if output_dir.exists():
        for status_file in sorted(output_dir.glob("run-*/run_status.json"), reverse=True):
            rid = status_file.parent.name.removeprefix("run-")
            if rid not in seen:
                try:
                    runs.append(RunStatus(**json.loads(status_file.read_text())))
                except Exception:
                    pass

    return sorted(runs, key=lambda r: r.run_id, reverse=True)


@app.get("/runs/{run_id}/report")
async def get_report(run_id: str, output: str = "reports") -> dict:
    """Return the report.json for a completed run."""
    report_file = Path(output) / f"run-{run_id}" / "report.json"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Report for run '{run_id}' not found")
    return json.loads(report_file.read_text())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
