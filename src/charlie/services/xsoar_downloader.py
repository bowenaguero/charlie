from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

_REQUIRED_ENV = ("DEMISTO_BASE_URL", "DEMISTO_API_KEY")

# demisto-sdk download requires the output path to be inside a Packs/ directory.
# We create this structure under the content root so callers don't need to know
# about the constraint.
_PACK_SUBDIR = Path("Packs") / "Custom"

log = logging.getLogger(__name__)


def download_xsoar_content(content_root: Path) -> None:
    missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    sdk_path = shutil.which("demisto-sdk")
    if sdk_path is None:
        raise RuntimeError("demisto-sdk not found. Install it with: pip install demisto-sdk")
    log.debug("demisto-sdk found at %s", sdk_path)

    pack_dir = content_root / _PACK_SUBDIR
    log.debug("pack_dir: %s (exists=%s)", pack_dir, pack_dir.exists())
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True)

    cmd = ["demisto-sdk", "download", "--all-custom-content", "--insecure", "--output", str(pack_dir)]
    log.debug("running: %s", " ".join(cmd))
    log.debug("DEMISTO_BASE_URL=%s", os.environ.get("DEMISTO_BASE_URL", "<not set>"))

    result = subprocess.run(cmd, capture_output=True, text=True)
    log.debug("return code: %d", result.returncode)
    if result.stdout.strip():
        log.debug("stdout:\n%s", result.stdout.strip())
    if result.stderr.strip():
        log.debug("stderr:\n%s", result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(f"demisto-sdk download failed:\n{result.stderr.strip()}")
