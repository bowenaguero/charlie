from __future__ import annotations

import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from charlie.core.config import Config
from charlie.services.updater import _CACHE_KEY, _CACHE_TTL_SECONDS, UpdateChecker


@pytest.fixture()
def cfg(tmp_path):
    c = Config.__new__(Config)
    c._path = tmp_path / "config.json"
    c._path.parent.mkdir(parents=True, exist_ok=True)
    return c


@pytest.fixture()
def console():
    return Console(file=StringIO(), highlight=False)


@pytest.fixture()
def checker(cfg, console):
    return UpdateChecker(cfg, console)


# --- _is_newer ---


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("1.0.0", "0.1.2", True),
        ("0.2.0", "0.1.2", True),
        ("0.1.3", "0.1.2", True),
        ("0.1.2", "0.1.2", False),
        ("0.0.1", "0.1.2", False),
    ],
)
def test_is_newer(latest, current, expected):
    assert UpdateChecker._is_newer(latest, current) is expected


# --- cache behavior ---


def test_uses_cache_when_fresh(checker, cfg):
    cfg.save({_CACHE_KEY: {"latest_version": "0.2.0", "checked_at": time.time()}})
    with patch.object(UpdateChecker, "_fetch") as mock_fetch:
        result = checker._get_latest_version()
    assert result == "0.2.0"
    mock_fetch.assert_not_called()


def test_fetches_when_cache_stale(checker, cfg):
    stale_ts = time.time() - _CACHE_TTL_SECONDS - 1
    cfg.save({_CACHE_KEY: {"latest_version": "0.1.0", "checked_at": stale_ts}})
    with patch.object(UpdateChecker, "_fetch", return_value="0.2.0"):
        result = checker._get_latest_version()
    assert result == "0.2.0"


def test_fetches_when_no_cache(checker):
    with patch.object(UpdateChecker, "_fetch", return_value="0.2.0"):
        result = checker._get_latest_version()
    assert result == "0.2.0"


def test_fetch_and_cache_writes_to_config(checker, cfg):
    with patch.object(UpdateChecker, "_fetch", return_value="0.3.0"):
        checker._fetch_and_cache()
    data = cfg.load()
    assert data[_CACHE_KEY]["latest_version"] == "0.3.0"
    assert data[_CACHE_KEY]["checked_at"] == pytest.approx(time.time(), abs=5)


def test_fetch_and_cache_skips_write_on_none(checker, cfg):
    with patch.object(UpdateChecker, "_fetch", return_value=None):
        checker._fetch_and_cache()
    assert cfg.load() == {}


# --- _fetch parsing ---


def _mock_response(body: bytes) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_fetch_parses_versioned_tag():
    with patch("urllib.request.urlopen", return_value=_mock_response(b'{"tag_name": "v0.2.0"}')):
        result = UpdateChecker._fetch()
    assert result == "0.2.0"


def test_fetch_parses_tag_without_v_prefix():
    with patch("urllib.request.urlopen", return_value=_mock_response(b'{"tag_name": "0.2.0"}')):
        result = UpdateChecker._fetch()
    assert result == "0.2.0"


def test_fetch_returns_none_on_missing_tag():
    with patch("urllib.request.urlopen", return_value=_mock_response(b"{}")):
        result = UpdateChecker._fetch()
    assert result is None


# --- notification output ---


def test_notify_prints_when_update_available(cfg):
    buf = StringIO()
    con = Console(file=buf, highlight=False, width=200)
    checker = UpdateChecker(cfg, con)
    with patch.object(UpdateChecker, "_get_latest_version", return_value="9.9.9"):
        checker.notify_if_update_available()
    output = buf.getvalue()
    assert "9.9.9" in output
    assert "uv tool upgrade charlie" in output


def test_notify_silent_when_on_latest(cfg):
    from charlie import __version__

    buf = StringIO()
    con = Console(file=buf, highlight=False)
    checker = UpdateChecker(cfg, con)
    with patch.object(UpdateChecker, "_get_latest_version", return_value=__version__):
        checker.notify_if_update_available()
    assert buf.getvalue() == ""


def test_notify_silent_on_network_error(checker):
    with patch.object(UpdateChecker, "_get_latest_version", side_effect=OSError("timeout")):
        checker.notify_if_update_available()  # must not raise
