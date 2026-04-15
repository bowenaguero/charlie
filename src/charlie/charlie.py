from __future__ import annotations

import logging

import typer

from .commands.reindex import reindex
from .commands.scan import scan
from .commands.setup import setup

app = typer.Typer(help="Map XSOAR content pack dependencies.", add_completion=False)


@app.callback()
def _main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")


app.command()(setup)
app.command()(scan)
app.command()(reindex)
