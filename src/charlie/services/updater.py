from __future__ import annotations

import json
import re
import time
import urllib.request

from rich.console import Console

from .. import __version__
from ..core.config import Config

_GITHUB_RELEASES_URL = "https://api.github.com/repos/bowenaguero/charlie/releases/latest"
_CACHE_KEY = "update_check"
_CACHE_TTL_SECONDS = 86_400
_TAG_RE = re.compile(r"v?(\d+\.\d+\.\d+)")


class UpdateChecker:
    def __init__(self, config: Config, console: Console) -> None:
        self._config = config
        self._console = console

    def notify_if_update_available(self) -> None:
        try:
            latest = self._get_latest_version()
            if latest and self._is_newer(latest, __version__):
                self._console.print(
                    f"\n[dim]A new version of charlie is available: [bold]{latest}[/bold] "
                    f"(current: {__version__}). "
                    "Run [cyan]uv tool upgrade charlie[/cyan] to update.[/dim]\n"
                )
        except Exception:  # noqa: S110
            pass

    def _get_latest_version(self) -> str | None:
        data = self._config.load()
        cache = data.get(_CACHE_KEY, {})
        if time.time() - cache.get("checked_at", 0.0) < _CACHE_TTL_SECONDS:
            return cache.get("latest_version")
        return self._fetch_and_cache()

    def _fetch_and_cache(self) -> str | None:
        latest = self._fetch()
        if latest is not None:
            data = self._config.load()
            data[_CACHE_KEY] = {"latest_version": latest, "checked_at": time.time()}
            self._config.save(data)
        return latest

    @staticmethod
    def _fetch() -> str | None:
        # S310: URL is a module-level constant with https scheme — not user-controlled.
        req = urllib.request.Request(  # noqa: S310
            _GITHUB_RELEASES_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "charlie-cli"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode())
        m = _TAG_RE.search(payload.get("tag_name", ""))
        return m.group(1) if m else None

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        try:
            return tuple(int(x) for x in latest.split(".")) > tuple(int(x) for x in current.split("."))
        except ValueError:
            return False
