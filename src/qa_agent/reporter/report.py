"""
Generates report.json + report.md for a completed run.
Reporter uses LiteLLM — works with any provider (Anthropic, Ollama, etc.).
Default: claude-haiku for Anthropic, qwen2.5:7b for Ollama.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from qa_agent.llm import LLMConfig, complete

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _reporter_system() -> str:
    return (_PROMPTS_DIR / "reporter_system.md").read_text()


def generate_report(
    results: list[dict],
    run_meta: dict,
    config: LLMConfig | None = None,
) -> str:
    """Call the configured LLM to produce a markdown report. Returns markdown string."""
    if config is None:
        config = LLMConfig.from_env(role="reporter")

    user_content = (
        f"Product: {run_meta.get('name', 'Unknown')}\n"
        f"Run ID: {run_meta['run_id']}\n"
        f"Target: {run_meta['url']}\n"
        f"Date: {run_meta['started_at']}\n\n"
        f"Results:\n{json.dumps(results, indent=2, ensure_ascii=False)}"
    )
    response = complete(
        config,
        messages=[
            {"role": "system", "content": _reporter_system()},
            {"role": "user", "content": user_content},
        ],
        max_tokens=2048,
    )
    return response.choices[0].message.content


def write_run(
    results: list[dict],
    spec_bundle,
    url: str,
    output_dir: Path,
    env: str | None = None,
) -> Path:
    """
    Write the full run artefacts to output_dir:
      report.json    — machine-readable, stable schema v1.0
      report.md      — human-friendly markdown (via LLM)
      telemetry.json — token/action counts
    Returns the run directory Path.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = output_dir / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence").mkdir(exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") == "fail")
    errored = sum(1 for r in results if r.get("status") == "error")

    run_meta = {
        "run_id": run_id,
        "name": spec_bundle.config.name,
        "url": url,
        "environment": env or spec_bundle.config.default_environment,
        "started_at": started_at,
    }

    # --- report.json ---
    report_json = {
        "schema_version": "1.0",
        **run_meta,
        "spec_path": spec_bundle.source_dir,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errored": errored,
        },
        "results": [_format_result(r) for r in results],
        "report_markdown": "report.md",
    }
    (run_dir / "report.json").write_text(
        json.dumps(report_json, indent=2, ensure_ascii=False)
    )

    # --- report.md (via LLM) ---
    reporter_config = LLMConfig.from_env(role="reporter")
    try:
        md = generate_report(results, run_meta, reporter_config)
    except Exception as e:
        md = f"# QA Report\n\nReport generation failed: {e}\n"
    (run_dir / "report.md").write_text(md)

    # --- telemetry.json ---
    total_actions = sum(len(r.get("actions_log", [])) for r in results)
    total_duration = sum(r.get("duration_s", 0) for r in results)
    telemetry = {
        "run_id": run_id,
        "reporter_provider": reporter_config.provider,
        "reporter_model": reporter_config.resolved_model(),
        "total_actions": total_actions,
        "total_duration_s": round(total_duration, 1),
        "requirements_count": len(results),
        "avg_actions_per_requirement": round(total_actions / max(len(results), 1), 1),
    }
    (run_dir / "telemetry.json").write_text(
        json.dumps(telemetry, indent=2, ensure_ascii=False)
    )

    return run_dir


def _format_result(r: dict) -> dict:
    return {
        "requirement_id": r.get("id", "unknown"),
        "title": r.get("title", ""),
        "status": r.get("status", "unknown"),
        "priority": r.get("priority", "medium"),
        "duration_ms": int(r.get("duration_s", 0) * 1000),
        "expected": r.get("then", ""),
        "actual": r.get("actual", ""),
        "reasoning": r.get("reasoning", ""),
        "evidence": {
            "actions_log": r.get("actions_log", []),
            "screenshots": [],
            "dom_snapshot": None,
            "console_errors": [],
        },
        "code_hints": None,
    }
