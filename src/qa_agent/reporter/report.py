"""
Generates report.json + report.md for a completed run.
report.md is built from a deterministic Python template — no LLM involved.
This guarantees consistent, correct output regardless of which LLM provider
was used for testing.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def _actions_summary(actions_log: list[dict]) -> str:
    parts = []
    for a in actions_log:
        tool = a.get("tool", "")
        inp = a.get("input", {})
        key_arg = inp.get("url") or inp.get("ref") or inp.get("text") or inp.get("value") or ""
        parts.append(f"{tool}({key_arg})" if key_arg else tool)
    return " → ".join(parts) if parts else "—"


def generate_report(results: list[dict], run_meta: dict) -> str:
    """Build a markdown report from results using a Python template. No LLM call."""
    name = run_meta.get("name", "Unknown")
    run_id = run_meta.get("run_id", "—")
    url = run_meta.get("url", "—")
    date = run_meta.get("started_at", "—")

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = len(results) - passed

    lines = [
        f"# QA Report — {name}",
        f"**Run:** {run_id}  |  **Target:** {url}  |  **Date:** {date}",
        "",
        "## Summary",
        "| Total | Passed | Failed |",
        "|-------|--------|--------|",
        f"| {len(results)} | {passed} | {failed} |",
        "",
        "## Results",
        "",
    ]

    failures = []
    for r in results:
        status = r.get("status", "fail")
        is_pass = status == "pass"
        icon = "✓" if is_pass else "✗"
        req_id = r.get("id", "")
        title = r.get("title", "")
        actual = r.get("actual", "")

        lines.append(f"### {icon} {req_id} — {title}  `{'PASS' if is_pass else 'FAIL'}`")
        lines.append(f"**Actual:** {actual}")

        if not is_pass:
            reasoning = r.get("reasoning", "")
            expected = r.get("then", "")
            actions = _actions_summary(r.get("actions_log", []))
            lines.append(f"**Expected (Then):** {expected}")
            lines.append(f"**Reasoning:** {reasoning}")
            lines.append(f"**Actions taken:** {actions}")
            failures.append(r)

        lines.append("")

    if failures:
        lines += ["---", "## Failed requirements", ""]
        for r in failures:
            req_id = r.get("id", "")
            title = r.get("title", "")
            actual = r.get("actual", "")
            reasoning = r.get("reasoning", "")
            expected = r.get("then", "")
            actions = _actions_summary(r.get("actions_log", []))
            lines += [
                f"### ✗ {req_id} — {title}",
                f"**Actual:** {actual}",
                f"**Expected (Then):** {expected}",
                f"**Reasoning:** {reasoning}",
                f"**Actions taken:** {actions}",
                "",
            ]

    verdict = "All requirements passed." if failed == 0 else f"{failed} requirement(s) failed and require attention."
    lines.append(f"Overall verdict: {verdict}")

    return "\n".join(lines)


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

    # --- report.md (deterministic template, no LLM) ---
    md = generate_report(results, run_meta)
    (run_dir / "report.md").write_text(md)

    # --- telemetry.json ---
    total_actions = sum(len(r.get("actions_log", [])) for r in results)
    total_duration = sum(r.get("duration_s", 0) for r in results)

    # Aggregate token usage from individual scenario results
    agg: dict[str, int | float] = {}
    per_scenario_usage = []
    for r in results:
        u = r.get("usage") or {}
        for key in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"):
            agg[key] = agg.get(key, 0) + u.get(key, 0)
        if "cost_usd" in u:
            agg["cost_usd"] = round(agg.get("cost_usd", 0.0) + u["cost_usd"], 6)
        if u:
            per_scenario_usage.append({
                "requirement_id": r.get("id", ""),
                **{k: u[k] for k in ("input_tokens", "output_tokens",
                                     "cache_write_tokens", "cache_read_tokens",
                                     "cost_usd") if k in u},
            })

    telemetry: dict = {
        "run_id": run_id,
        "requirements_count": len(results),
        "total_actions": total_actions,
        "total_duration_s": round(total_duration, 1),
        "avg_actions_per_requirement": round(total_actions / max(len(results), 1), 1),
        "report_generated_by": "template",
    }
    if agg:
        telemetry["tokens"] = agg
    if per_scenario_usage:
        telemetry["per_scenario"] = per_scenario_usage

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
