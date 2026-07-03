from __future__ import annotations

import os
from pathlib import Path

SCHEMA_VERSION = 1
STATUS_STALE_AFTER_SECONDS = float(os.environ.get("PSC_CONTROL_STATUS_STALE_AFTER_SECONDS", "15"))


def control_root() -> Path:
    override = os.environ.get("PSC_CONTROL_ROOT")
    if override:
        return Path(override)
    return Path.home() / ".agents" / "control"


def requests_dir() -> Path:
    return control_root() / "requests"


def done_dir() -> Path:
    return control_root() / "done"


def status_path() -> Path:
    return control_root() / "status.json"


def lock_path() -> Path:
    return control_root() / "manager.lock"
