from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_REQUIRED_ENV = ("DEMISTO_BASE_URL", "DEMISTO_API_KEY")

# demisto-sdk download requires the output path to be inside a Packs/ directory.
# We create this structure under the content root so callers don't need to know
# about the constraint.
_PACK_SUBDIR = Path("Packs") / "Custom"


def download_xsoar_content(content_root: Path) -> None:
    missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    if shutil.which("demisto-sdk") is None:
        raise RuntimeError("demisto-sdk not found. Install it with: pip install demisto-sdk")

    pack_dir = content_root / _PACK_SUBDIR
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True)

    result = subprocess.run(
        ["demisto-sdk", "download", "--all-custom-content", "--output", str(pack_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"demisto-sdk download failed:\n{result.stderr.strip()}")
