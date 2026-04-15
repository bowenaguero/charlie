from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from ..core.config import Config

_console = Console()


def setup() -> None:
    """Configure charlie and sync the content repo (run this first)."""
    cfg = Config()

    _console.print("[bold cyan]charlie setup[/bold cyan]")
    _console.print("─" * 50)

    source = typer.prompt("Content source [git/xsoar]", default="git").strip().lower()
    if source not in ("git", "xsoar"):
        _console.print("[red]error:[/red] choose 'git' or 'xsoar'")
        raise typer.Exit(1)

    cfg.set_content_source(source)

    if source == "git":
        _git_setup(cfg)
    else:
        _xsoar_setup(cfg)

    _console.print(f"\n[green]✓[/green] Config saved to [bold]{cfg.path}[/bold]")
    _console.print("\nRun [bold]charlie scan --target <name> --type <type>[/bold]")


def _git_setup(cfg: Config) -> None:
    current_url = cfg.get_repo_url()

    if current_url:
        _console.print(f"Current repo: [dim]{current_url}[/dim]")
    else:
        _console.print("[dim]No repo configured yet.[/dim]")

    _console.print()

    url = typer.prompt(
        "Git URL of XSOAR content repo",
        default=current_url or "",
    ).strip()

    if not url:
        _console.print("[red]error:[/red] URL cannot be empty")
        raise typer.Exit(1)

    local_path = cfg.repo_local_path
    url_changed = current_url is not None and url != current_url

    if url_changed and local_path.exists():
        _console.print("[yellow]URL changed — removing existing clone…[/yellow]")
        shutil.rmtree(local_path)

    cfg.set_repo_url(url)

    if local_path.exists():
        _git_pull(local_path)
    else:
        _git_clone(url, local_path)

    run_index(cfg)


def _xsoar_setup(cfg: Config) -> None:
    from ..services.xsoar_downloader import _REQUIRED_ENV, download_xsoar_content

    for var in _REQUIRED_ENV:
        if not os.environ.get(var):
            _console.print(f"[red]error:[/red] env var [bold]{var}[/bold] is not set")
            raise typer.Exit(1)

    with _console.status("Downloading content from XSOAR instance…"):
        try:
            download_xsoar_content(cfg.repo_local_path)
        except RuntimeError as e:
            _console.print(f"[red]error:[/red] {e}")
            raise typer.Exit(1) from e

    run_index(cfg)


def run_index(cfg: Config) -> None:
    from ..services.indexer import build_index

    with _console.status("Indexing repo…"):
        stats = build_index(cfg.repo_local_path, cfg.db_path)
    _console.print(
        f"[green]✓[/green] Indexed [bold]{stats.files_indexed}[/bold] files, "
        f"[bold]{stats.refs_found}[/bold] refs in [dim]{stats.duration_s:.1f}s[/dim]"
    )


def _git_clone(url: str, dest: Path) -> None:
    with _console.status(f"Cloning [bold]{url}[/bold]…"):
        result = subprocess.run(
            ["git", "clone", url, str(dest)],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        _console.print(f"[red]error:[/red] git clone failed:\n{result.stderr.strip()}")
        raise typer.Exit(1)
    _console.print(f"[green]✓[/green] Cloned to [bold]{dest}[/bold]")


def _git_pull(local_path: Path) -> None:
    with _console.status("Pulling latest changes…"):
        result = subprocess.run(
            ["git", "-C", str(local_path), "pull"],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        _console.print(f"[red]error:[/red] git pull failed:\n{result.stderr.strip()}")
        raise typer.Exit(1)
    _console.print(f"[green]✓[/green] Repo updated ({result.stdout.strip()})")
