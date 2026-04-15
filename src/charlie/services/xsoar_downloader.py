from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_REQUIRED_ENV = ("DEMISTO_BASE_URL", "DEMISTO_API_KEY")


def download_xsoar_content(dest: Path) -> None:
    missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    if shutil.which("demisto-sdk") is None:
        raise RuntimeError("demisto-sdk not found. Install it with: pip install demisto-sdk")

    dest.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["demisto-sdk", "download", "--all-custom-content", "--output", str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"demisto-sdk download failed:\n{result.stderr.strip()}")
