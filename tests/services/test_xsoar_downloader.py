from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from charlie.services.xsoar_downloader import download_xsoar_content


@pytest.fixture()
def env_vars(monkeypatch):
    monkeypatch.setenv("DEMISTO_BASE_URL", "https://xsoar.example.com")
    monkeypatch.setenv("DEMISTO_API_KEY", "test-api-key")


def test_missing_base_url_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMISTO_BASE_URL", raising=False)
    monkeypatch.setenv("DEMISTO_API_KEY", "key")
    with pytest.raises(RuntimeError, match="DEMISTO_BASE_URL"):
        download_xsoar_content(tmp_path / "content")


def test_missing_api_key_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMISTO_BASE_URL", "https://xsoar.example.com")
    monkeypatch.delenv("DEMISTO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEMISTO_API_KEY"):
        download_xsoar_content(tmp_path / "content")


def test_missing_both_env_vars_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMISTO_BASE_URL", raising=False)
    monkeypatch.delenv("DEMISTO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEMISTO_BASE_URL"):
        download_xsoar_content(tmp_path / "content")


def test_missing_demisto_sdk_raises(env_vars, tmp_path):
    with patch("shutil.which", return_value=None), pytest.raises(RuntimeError, match="demisto-sdk not found"):
        download_xsoar_content(tmp_path / "content")


def test_successful_download(env_vars, tmp_path):
    dest = tmp_path / "content"
    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("shutil.which", return_value="/usr/local/bin/demisto-sdk"),
        patch("subprocess.run", return_value=mock_result) as mock_run,
    ):
        download_xsoar_content(dest)

    assert dest.exists()
    mock_run.assert_called_once_with(
        ["demisto-sdk", "download", "--all-custom-content", "--output", str(dest)],
        capture_output=True,
        text=True,
    )


def test_failed_download_raises(env_vars, tmp_path):
    dest = tmp_path / "content"
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "connection refused"

    with (
        patch("shutil.which", return_value="/usr/local/bin/demisto-sdk"),
        patch("subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="connection refused"),
    ):
        download_xsoar_content(dest)
