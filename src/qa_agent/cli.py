"""CLI entrypoint — qa-agent run --spec <dir>"""
import asyncio
import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich import box

from qa_agent.agent import run_requirement
from qa_agent.specs import load_spec

app = typer.Typer(help="QA Agent — spec-driven automated testing.", add_completion=False)
console = Console()


async def _run_all(spec_dir: Path, env: str | None) -> list[dict]:
    bundle = load_spec(spec_dir)
    url = bundle.config.get_url(env)

    console.print(f"\n[bold]{bundle.config.name}[/bold]  [dim]{url}[/dim]")
    console.print(f"[dim]{len(bundle.requirements)} requirements from {spec_dir}[/dim]\n")

    results = []
    for req in bundle.requirements:
        result = await run_requirement(req.to_executor_dict(), url)
        results.append(result)
        console.print()

    return results


def _print_summary(results: list[dict], total_duration: float) -> None:
    console.rule("Summary")

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Status", justify="center")
    table.add_column("Actions", justify="right")
    table.add_column("Time", justify="right")

    for r in results:
        is_pass = r["status"] == "pass"
        status_str = "[green]✓ PASS[/green]" if is_pass else "[red]✗ FAIL[/red]"
        table.add_row(
            r["id"],
            r.get("title", ""),
            status_str,
            str(len(r.get("actions_log", []))),
            f"{r.get('duration_s', 0)}s",
        )

    console.print(table)

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = len(results) - passed
    color = "green" if failed == 0 else "red"
    console.print(
        f"[{color}][bold]{passed} passed[/bold][/{color}], "
        f"[red]{failed} failed[/red]  "
        f"[dim]│  total {round(total_duration)}s[/dim]\n"
    )


@app.command()
def run(
    spec: Path = typer.Argument(..., help="Path to spec directory"),
    env: str = typer.Option(None, "--env", help="Environment name (default: from config.yaml)"),
    output: Path = typer.Option(None, "--output", help="Write results JSON to this path"),
):
    """Run all requirements from a spec directory."""
    start = time.monotonic()
    try:
        results = asyncio.run(_run_all(spec, env))
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    total = round(time.monotonic() - start, 1)
    _print_summary(results, total)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        console.print(f"[dim]Results written to {output}[/dim]")

    failed = sum(1 for r in results if r["status"] != "pass")
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


if __name__ == "__main__":
    app()
