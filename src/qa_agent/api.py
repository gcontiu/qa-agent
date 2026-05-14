"""
FastAPI HTTP wrapper for qa-agent.

Endpoints:
  POST /products                              — create a product record
  GET  /products                              — list all products
  GET  /products/{id}                         — get product
  POST /products/{id}/analyze                 — run analyst + save specs to DB (202 Accepted)
  GET  /products/{id}/analyze/{task_id}       — poll analysis status
  GET  /products/{id}/specs                   — list specs for a product
  GET  /products/{id}/specs/{filename}        — get spec content
  PUT  /products/{id}/specs/{filename}        — create / update spec content
  DELETE /products/{id}/specs/{filename}      — delete spec
  POST /products/{id}/specs/{filename}/approve — set approved flag

  POST /runs                     — create a run; accepts spec_dir or product_id (202 Accepted)
  GET  /runs                     — list all runs (in-memory + disk)
  GET  /runs/{run_id}            — poll run status
  POST /runs/{run_id}/cancel     — cancel a pending/running run (202; 409 if already terminal)
  GET  /runs/{run_id}/report     — return report.json
  GET  /health                   — liveness probe
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel

from qa_agent.agent import preflight_check, run_requirement
from qa_agent.analyst import run_analysis
from qa_agent.llm import LLMConfig
from qa_agent.reporter import write_run
from qa_agent.specs import load_spec
from qa_agent.state import StateStore
from qa_agent.db import init as db_init, close as db_close
from qa_agent.db import jobs as db_jobs
from qa_agent.db import products as db_products
from qa_agent.db import specs as db_specs

app = FastAPI(title="qa-agent", version="0.1.0")

_DEFAULT_REPORTS_DIR = Path("reports")
_STATE_DB = Path("reports/.state/runs.db")

# In-memory registry: run_id → status dict.
# Dual-written to Postgres when DATABASE_URL is set.
_runs: dict[str, dict] = {}

# Task registry: run_id → asyncio.Task (for cancellation).
_tasks: dict[str, asyncio.Task] = {}

# In-memory registry for analysis tasks (not persisted to DB yet).
_analyses: dict[str, dict] = {}


@app.on_event("startup")
async def _startup() -> None:
    await db_init()
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

    results: list[dict] = []
    try:
        for i, req_item in enumerate(requirements):
            if i > 0 and scenario_delay > 0:
                await asyncio.sleep(scenario_delay)
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/runs", response_model=RunStatus, status_code=202)
async def create_run(req: RunRequest) -> RunStatus:
    """Start a QA run. Returns immediately with run_id; poll GET /runs/{run_id} for status."""
    if not req.spec_dir and not req.product_id:
        raise HTTPException(status_code=422, detail="Either spec_dir or product_id must be provided")

    if req.product_id:
        product = await db_products.get(req.product_id)
        slug = product["name"].lower().replace(" ", "-") if product else "product"
    else:
        slug = Path(req.spec_dir).name.lower()
    run_id = f"{slug}-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
    output_dir = Path(req.output)
    spec_key = req.spec_dir or f"product:{req.product_id}"

    state: dict = {
        "run_id": run_id,
        "status": "pending",
        "spec_dir": spec_key,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _runs[run_id] = state
    _write_status_file(output_dir, run_id, state)
    await db_jobs.create(run_id, spec_key,
                         executor_model=req.executor_model,
                         max_scenarios=req.max_scenarios)

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


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.post("/products", status_code=201)
async def create_product(req: ProductRequest) -> dict:
    product_id = await db_products.create(req.name, req.url, req.description)
    product = await db_products.get(product_id)
    return product


@app.get("/products")
async def list_products() -> list[dict]:
    return await db_products.list_all()


@app.get("/products/{product_id}")
async def get_product(product_id: str) -> dict:
    product = await db_products.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    return product


# ---------------------------------------------------------------------------
# Analysis (analyst runs in background, saves specs to DB)
# ---------------------------------------------------------------------------

async def _run_analysis_task(task_id: str, product_id: str, req: AnalyzeRequest) -> None:
    state = _analyses[task_id]
    try:
        output_dir = _DEFAULT_REPORTS_DIR / "analyses" / task_id
        result = await run_analysis(
            url=req.url,
            description=req.description,
            output_dir=output_dir,
            spec_prefix=req.spec_prefix,
            pages=req.pages,
            product_id=product_id,
        )
        state.update({
            "status": "done",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "files_written": result["files_written"],
            "file_count": result["file_count"],
            "summary": result["summary"],
            "cost_usd": result.get("cost_usd"),
        })
    except Exception as e:
        state.update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })


@app.post("/products/{product_id}/analyze", status_code=202)
async def analyze_product(product_id: str, req: AnalyzeRequest) -> dict:
    """Trigger analyst for a product. Saves generated specs to DB. Poll with GET."""
    product = await db_products.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    task_id = f"analyze-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
    state: dict = {
        "task_id": task_id,
        "product_id": product_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _analyses[task_id] = state
    asyncio.create_task(_run_analysis_task(task_id, product_id, req))
    return state


@app.get("/products/{product_id}/analyze/{task_id}")
async def get_analysis_task(product_id: str, task_id: str) -> dict:
    state = _analyses.get(task_id)
    if not state or state.get("product_id") != product_id:
        raise HTTPException(status_code=404, detail=f"Analysis task '{task_id}' not found")
    return state


# ---------------------------------------------------------------------------
# Specs CRUD
# ---------------------------------------------------------------------------

@app.get("/products/{product_id}/specs")
async def list_specs(product_id: str) -> list[dict]:
    return await db_specs.list_by_product(product_id)


@app.get("/products/{product_id}/specs/{filename:path}")
async def get_spec(product_id: str, filename: str) -> dict:
    spec = await db_specs.get_by_filename(product_id, filename)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Spec '{filename}' not found")
    return spec


@app.put("/products/{product_id}/specs/{filename:path}", status_code=200)
async def upsert_spec(product_id: str, filename: str, req: SpecUpdateRequest) -> dict:
    await db_specs.upsert(product_id, filename, req.content)
    return await db_specs.get_by_filename(product_id, filename)


@app.delete("/products/{product_id}/specs/{filename:path}", status_code=204)
async def delete_spec(product_id: str, filename: str) -> None:
    deleted = await db_specs.delete(product_id, filename)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Spec '{filename}' not found")


@app.post("/products/{product_id}/specs/{filename:path}/approve")
async def approve_spec(product_id: str, filename: str, req: ApproveRequest = Body(default=ApproveRequest())) -> dict:
    updated = await db_specs.set_approved(product_id, filename, req.approved)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Spec '{filename}' not found")
    return await db_specs.get_by_filename(product_id, filename)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
