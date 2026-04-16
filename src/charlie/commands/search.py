from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console

from ..core.config import Config
from ..core.models import ComponentType
from ..services.db import list_components
from ..services.scanner import scan as scan_repo
from ..utils.display import export_dot, render_html, render_tree
from ..utils.graph import build_graph

_console = Console()


def _render(
    result,
    output: str,
    html_out: Path,
    dot_out: Path,
    open_browser: bool,
) -> None:
    match output:
        case "tree":
            render_tree(result, _console)
        case "html":
            graph = build_graph(result)
            render_html(graph, html_out)
            _console.print(f"[green]✓[/green] HTML graph written to [bold]{html_out}[/bold]")
            if open_browser:
                webbrowser.open(html_out.resolve().as_uri())
        case "dot":
            graph = build_graph(result)
            export_dot(graph, dot_out)
            _console.print(f"[green]✓[/green] DOT file written to [bold]{dot_out}[/bold]")
        case _:
            _console.print(f"[red]error:[/red] unknown output format '{output}'. Choose: tree, html, dot")
            raise typer.Exit(1)


def search(
    component_type: Annotated[
        ComponentType | None,
        typer.Option("--type", "-t", help="Pre-filter to a specific component type before entering interactive mode"),
    ] = None,
    output: str = typer.Option("tree", "--output", "-o", help="Output format: tree | html | dot"),
    html_out: Path = typer.Option(Path("charlie_output.html"), "--html-out", help="HTML output path"),
    dot_out: Path = typer.Option(Path("charlie_output.dot"), "--dot-out", help="DOT output path"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open HTML in browser after writing"),
) -> None:
    """Interactively search indexed components and scan dependencies for the selected one."""
    cfg = Config()

    if not cfg.db_path.exists():
        _console.print("[red]error:[/red] no index found. Run [bold]charlie setup[/bold] first.")
        raise typer.Exit(1)

    if not sys.stdin.isatty():
        _console.print("[red]error:[/red] search requires an interactive terminal.")
        raise typer.Exit(1)

    components = list_components(cfg.db_path, component_type)

    if not components:
        type_hint = f" of type [bold]{component_type.value}[/bold]" if component_type else ""
        _console.print(f"[yellow]no indexed components found{type_hint}.[/yellow]")
        raise typer.Exit(0)

    if component_type is not None:
        choices = [Choice(value=(name, ct), name=name) for name, ct in components]
    else:
        choices = [Choice(value=(name, ct), name=f"{name}  ({ct.value})") for name, ct in components]

    try:
        selected = inquirer.fuzzy(
            message="Select a component to scan:",
            choices=choices,
            max_height="40%",
            border=True,
            info=True,
            multiselect=False,
        ).execute()
    except KeyboardInterrupt:
        raise typer.Exit(0) from None

    if selected is None:
        raise typer.Exit(0)

    target_name, target_type = selected

    if not cfg.repo_local_path.exists():
        _console.print("[red]error:[/red] no repo found. Run [bold]charlie setup[/bold] first.")
        raise typer.Exit(1)

    _console.print(f"\nScanning for references to [bold]{target_name}[/bold] [dim]({target_type.value})[/dim]…")

    result = scan_repo(cfg.repo_local_path, target_name, target_type, db_path=cfg.db_path)
    _render(result, output, html_out, dot_out, open_browser)
