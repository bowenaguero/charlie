from __future__ import annotations

import typer
from rich.console import Console

from ..core.config import Config
from .setup import run_index

_console = Console()


def reindex() -> None:
    """Re-index the content repo (run after pulling changes manually)."""
    cfg = Config()
    if not cfg.repo_local_path.exists():
        _console.print("[red]error:[/red] no repo found. Run [bold]charlie setup[/bold] first.")
        raise typer.Exit(1)
    run_index(cfg)
