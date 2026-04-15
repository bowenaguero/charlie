from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from ..core.config import Config
from ..core.models import ComponentType
from ..services.scanner import scan as scan_repo
from ..utils.display import export_dot, render_html, render_tree
from ..utils.graph import build_graph

_console = Console()


def scan(
    target: str = typer.Option(..., "--target", "-t", help="Name of the component to trace"),
    component_type: ComponentType = typer.Option(..., "--type", help="Component type to trace"),
    repo: Annotated[Optional[Path], typer.Option("--repo", "-r", help="Override repo path (skips managed clone)")] = None,
    output: str = typer.Option("tree", "--output", "-o", help="Output format: tree | html | dot"),
    html_out: Path = typer.Option(Path("charlie_output.html"), "--html-out", help="HTML output path"),
    dot_out: Path = typer.Option(Path("charlie_output.dot"), "--dot-out", help="DOT output path"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open HTML in browser after writing"),
) -> None:
    """Scan the content repo for all components that depend on TARGET."""
    cfg = Config()

    if repo is not None:
        resolved_repo = repo
    elif cfg.repo_local_path.exists():
        resolved_repo = cfg.repo_local_path
    else:
        _console.print("[red]error:[/red] no repo found. Run [bold]charlie setup[/bold] first.")
        raise typer.Exit(1)

    if not resolved_repo.exists():
        _console.print(f"[red]error:[/red] repo path does not exist: {resolved_repo}")
        raise typer.Exit(1)

    _console.print(
        f"Scanning for references to [bold]{target}[/bold] [dim]({component_type.value})[/dim]…"
    )

    result = scan_repo(resolved_repo, target, component_type, db_path=cfg.db_path)

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
