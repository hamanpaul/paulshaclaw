from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path


def test_version_file_matches_pyproject() -> None:
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

    assert version == pyproject


def test_latest_version_tag_matches_if_any() -> None:
    root = Path(__file__).resolve().parents[1]
    tags = subprocess.run(
        ["git", "tag", "--list", "v*"],
        capture_output=True,
        check=False,
        cwd=root,
        text=True,
    ).stdout.split()
    if not tags:
        return

    latest = sorted(tags, key=lambda tag: [int(part) for part in re.sub(r"^v", "", tag).split(".")])[-1]
    assert re.sub(r"^v", "", latest) == (root / "VERSION").read_text(encoding="utf-8").strip()
