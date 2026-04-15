import json
from pathlib import Path

import pytest

from charlie.core.config import Config


@pytest.fixture()
def cfg(tmp_path):
    c = Config.__new__(Config)
    c._path = tmp_path / "config.json"
    c._path.parent.mkdir(parents=True, exist_ok=True)
    return c


def test_load_returns_empty_when_no_file(cfg):
    assert cfg.load() == {}


def test_get_repo_url_returns_none_when_unconfigured(cfg):
    assert cfg.get_repo_url() is None


def test_set_and_get_repo_url(cfg):
    cfg.set_repo_url("https://github.com/example/content")
    assert cfg.get_repo_url() == "https://github.com/example/content"


def test_save_writes_json(cfg):
    cfg.save({"repo_url": "https://github.com/example/content"})
    raw = json.loads(cfg.path.read_text())
    assert raw["repo_url"] == "https://github.com/example/content"


def test_load_handles_corrupt_file(cfg):
    cfg.path.write_text("not json", encoding="utf-8")
    assert cfg.load() == {}


def test_set_repo_url_preserves_other_keys(cfg):
    cfg.save({"other_key": "other_value"})
    cfg.set_repo_url("https://github.com/example/content")
    data = cfg.load()
    assert data["other_key"] == "other_value"
    assert data["repo_url"] == "https://github.com/example/content"


def test_repo_local_path_is_a_path(cfg):
    assert isinstance(cfg.repo_local_path, Path)
