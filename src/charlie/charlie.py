from __future__ import annotations

import typer

from .commands.reindex import reindex
from .commands.scan import scan
from .commands.setup import setup

app = typer.Typer(help="Map XSOAR content pack dependencies.", add_completion=False)

app.command()(setup)
app.command()(scan)
app.command()(reindex)
