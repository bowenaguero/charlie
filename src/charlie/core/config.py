from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

_CONFIG_FILE = Path(user_config_dir("charlie", appauthor=False)) / "config.json"
_REPO_CLONE_PATH = Path(user_data_dir("charlie", appauthor=False)) / "repo"


class Config:
    def __init__(self) -> None:
        self._path = _CONFIG_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _REPO_CLONE_PATH.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def repo_local_path(self) -> Path:
        return _REPO_CLONE_PATH

    @property
    def db_path(self) -> Path:
        return _REPO_CLONE_PATH.parent / "index.db"

    def load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_repo_url(self) -> str | None:
        return self.load().get("repo_url")

    def set_repo_url(self, url: str) -> None:
        data = self.load()
        data["repo_url"] = url
        self.save(data)

    def get_content_source(self) -> str:
        return self.load().get("content_source", "git")

    def set_content_source(self, source: str) -> None:
        data = self.load()
        data["content_source"] = source
        self.save(data)
