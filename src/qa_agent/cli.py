"""CLI entrypoint — qa-agent run --spec <dir>"""
import asyncio
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from qa_agent.agent import run_requirement
from qa_agent.reporter import write_run
from qa_agent.specs import load_spec
from qa_agent.state import StateStore

app = typer.Typer(help="QA Agent — spec-driven automated testing.", add_completion=False)
console = Console()

_DEFAULT_REPORTS_DIR = Path("reports")
_STATE_DB = Path("reports/.state/runs.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _execute_requirements(requirements, url: str) -> list[dict]:
    results = []
    for req in requirements:
        result = await run_requirement(req.to_executor_dict(), url)
        results.append(result)
        console.print()
    return results


def _print_summary(results: list[dict], skipped: list[dict], total_duration: float, run_dir: Path) -> None:
    console.rule("Summary")

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Status", justify="center")
    table.add_column("Actions", justify="right")
    table.add_column("Time", justify="right")

    for r in results:
        is_pass = r.get("status") == "pass"
        status_str = "[green]✓ PASS[/green]" if is_pass else "[red]✗ FAIL[/red]"
        table.add_row(
            r.get("id", ""),
            r.get("title", ""),
            status_str,
            str(len(r.get("actions_log", []))),
            f"{r.get('duration_s', 0)}s",
        )

    for r in skipped:
        table.add_row(
            r.get("requirement_id", ""),
            r.get("title", ""),
            "[dim]— SKIP[/dim]",
            "—",
            "—",
        )

    console.print(table)

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") != "pass")
    color = "green" if failed == 0 else "red"

    skip_note = f", [dim]{len(skipped)} skipped (passed previously)[/dim]" if skipped else ""
    console.print(
        f"[{color}][bold]{passed} passed[/bold][/{color}], "
        f"[red]{failed} failed[/red]{skip_note}  "
        f"[dim]│  total {round(total_duration)}s[/dim]"
    )
    console.print(f"[dim]Report: {run_dir / 'report.md'}[/dim]\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def run(
    spec: Path = typer.Argument(..., help="Path to spec directory"),
    env: str = typer.Option(None, "--env", help="Environment name (default: from config.yaml)"),
    output: Path = typer.Option(_DEFAULT_REPORTS_DIR, "--output", help="Reports base directory"),
    only_failing: bool = typer.Option(False, "--only-failing", help="Re-run only requirements that failed in the last run"),
    previous: str = typer.Option(None, "--previous", help="Run ID to use as baseline for --only-failing"),
):
    """Run all requirements from a spec directory."""
    start = time.monotonic()

    try:
        bundle = load_spec(spec)
        url = bundle.config.get_url(env)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    store = StateStore(_STATE_DB)
    requirements = bundle.requirements
    skipped_results: list[dict] = []

    if only_failing:
        run_id = previous or store.last_run_id(str(spec))
        if not run_id:
            console.print("[yellow]No previous run found — running all requirements.[/yellow]")
        else:
            failing = store.failing_ids(run_id)
            if not failing:
                console.print(f"[green]All requirements passed in run {run_id}. Nothing to re-run.[/green]")
                store.close()
                raise typer.Exit(0)

            skipped_results = [
                r for r in store.get_results(run_id)
                if r["requirement_id"] not in failing
            ]
            requirements = [r for r in requirements if r.id in failing]
            console.print(
                f"[dim]--only-failing: re-running {len(requirements)} failed "
                f"({len(skipped_results)} skipped — passed previously)[/dim]"
            )

    console.print(f"\n[bold]{bundle.config.name}[/bold]  [dim]{url}[/dim]")
    console.print(f"[dim]{len(requirements)} requirements to run[/dim]\n")

    try:
        results = asyncio.run(_execute_requirements(requirements, url))
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        store.close()
        raise typer.Exit(2)

    total = round(time.monotonic() - start, 1)

    console.print("[dim]Writing report...[/dim]")
    run_dir = write_run(results, bundle, url, output, env)

    store.save_run(
        run_id=run_dir.name.removeprefix("run-"),
        spec_path=str(spec),
        url=url,
        environment=env or bundle.config.default_environment,
        started_at=run_dir.name.removeprefix("run-"),
        results=results,
    )
    store.close()

    _print_summary(results, skipped_results, total, run_dir)

    failed = sum(1 for r in results if r.get("status") != "pass")
    raise typer.Exit(1 if failed else 0)


@app.command()
def validate(
    spec: Path = typer.Argument(..., help="Path to spec directory"),
):
    """Validate spec directory structure and format."""
    try:
        bundle = load_spec(spec)
        console.print(f"[green]✓[/green] Valid — {len(bundle.requirements)} requirements found")
        for req in bundle.requirements:
            console.print(f"  [dim]{req.id}[/dim]  {req.title}")
    except Exception as e:
        console.print(f"[red]✗ Invalid:[/red] {e}")
        raise typer.Exit(2)


@app.command(name="list-runs")
def list_runs(
    spec: Path = typer.Option(None, "--spec", help="Filter by spec directory"),
    reports_dir: Path = typer.Option(_DEFAULT_REPORTS_DIR, "--reports-dir"),
):
    """List previous runs from the state store."""
    store = StateStore(reports_dir / ".state" / "runs.db")
    runs = store.list_runs(str(spec) if spec else None)
    store.close()

    if not runs:
        console.print("[dim]No runs recorded yet.[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Run ID")
    table.add_column("Spec")
    table.add_column("Total", justify="right")
    table.add_column("Passed", justify="right")
    table.add_column("Failed", justify="right")

    for r in runs:
        failed = r["failed"]
        fail_str = f"[red]{failed}[/red]" if failed else "[dim]0[/dim]"
        table.add_row(
            r["run_id"],
            Path(r["spec_path"]).name,
            str(r["total"]),
            f"[green]{r['passed']}[/green]",
            fail_str,
        )
    console.print(table)


@app.command(name="show-report")
def show_report(
    run_id: str = typer.Argument(..., help="Run ID (e.g. 2026-04-24T14-30-00Z)"),
    reports_dir: Path = typer.Option(_DEFAULT_REPORTS_DIR, "--reports-dir"),
    fmt: str = typer.Option("md", "--format", help="md or json"),
):
    """Print a previously generated report."""
    run_dir = reports_dir / f"run-{run_id}"
    target = run_dir / ("report.md" if fmt == "md" else "report.json")
    if not target.exists():
        console.print(f"[red]Not found:[/red] {target}")
        raise typer.Exit(2)
    console.print(target.read_text())


if __name__ == "__main__":
    app()
