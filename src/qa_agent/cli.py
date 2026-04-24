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

app = typer.Typer(help="QA Agent — spec-driven automated testing.", add_completion=False)
console = Console()
_DEFAULT_REPORTS_DIR = Path("reports")


async def _run_all(spec_dir: Path, env: str | None) -> tuple[list[dict], object, str]:
    bundle = load_spec(spec_dir)
    url = bundle.config.get_url(env)

    console.print(f"\n[bold]{bundle.config.name}[/bold]  [dim]{url}[/dim]")
    console.print(f"[dim]{len(bundle.requirements)} requirements from {spec_dir}[/dim]\n")

    results = []
    for req in bundle.requirements:
        result = await run_requirement(req.to_executor_dict(), url)
        results.append(result)
        console.print()

    return results, bundle, url


def _print_summary(results: list[dict], total_duration: float, run_dir: Path) -> None:
    console.rule("Summary")

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Status", justify="center")
    table.add_column("Actions", justify="right")
    table.add_column("Time", justify="right")

    for r in results:
        status = r.get("status", "unknown")
        is_pass = status == "pass"
        status_str = "[green]✓ PASS[/green]" if is_pass else "[red]✗ FAIL[/red]"
        table.add_row(
            r.get("id", ""),
            r.get("title", ""),
            status_str,
            str(len(r.get("actions_log", []))),
            f"{r.get('duration_s', 0)}s",
        )

    console.print(table)

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = len(results) - passed
    color = "green" if failed == 0 else "red"
    console.print(
        f"[{color}][bold]{passed} passed[/bold][/{color}], "
        f"[red]{failed} failed[/red]  "
        f"[dim]│  total {round(total_duration)}s[/dim]"
    )
    console.print(f"[dim]Report: {run_dir / 'report.md'}[/dim]\n")


@app.command()
def run(
    spec: Path = typer.Argument(..., help="Path to spec directory"),
    env: str = typer.Option(None, "--env", help="Environment name (default: from config.yaml)"),
    output: Path = typer.Option(_DEFAULT_REPORTS_DIR, "--output", help="Reports base directory"),
):
    """Run all requirements from a spec directory."""
    start = time.monotonic()
    try:
        results, bundle, url = asyncio.run(_run_all(spec, env))
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    total = round(time.monotonic() - start, 1)

    console.print("[dim]Writing report...[/dim]")
    run_dir = write_run(results, bundle, url, output, env)

    _print_summary(results, total, run_dir)

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
