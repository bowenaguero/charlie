from __future__ import annotations

import logging

import typer
from rich.console import Console

from ..core.config import Config
from .setup import run_index

_console = Console()
log = logging.getLogger(__name__)


def reindex() -> None:
    """Re-index the content repo (run after pulling changes manually)."""
    cfg = Config()
    log.debug("content_root: %s (exists=%s)", cfg.repo_local_path, cfg.repo_local_path.exists())

    if not cfg.repo_local_path.exists():
        _console.print("[red]error:[/red] no content found. Run [bold]charlie setup[/bold] first.")
        raise typer.Exit(1)

    if cfg.get_content_source() == "xsoar":
        from ..services.xsoar_downloader import download_xsoar_content

        log.debug("content_source=xsoar, starting download")
        with _console.status("Re-downloading content from XSOAR instance…"):
            try:
                download_xsoar_content(cfg.repo_local_path)
            except RuntimeError as e:
                _console.print(f"[red]error:[/red] {e}")
                raise typer.Exit(1) from e

    run_index(cfg)
