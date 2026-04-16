from __future__ import annotations

import logging

import typer
from rich.console import Console

from . import __version__
from .commands.reindex import reindex
from .commands.scan import scan
from .commands.setup import setup
from .core.config import Config
from .services.updater import UpdateChecker

app = typer.Typer(help="Map XSOAR content pack dependencies.", add_completion=False, no_args_is_help=True)

_console = Console()


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"charlie {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
        expose_value=False,
    ),
) -> None:
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    UpdateChecker(Config(), _console).notify_if_update_available()


app.command()(setup)
app.command()(scan)
app.command()(reindex)
