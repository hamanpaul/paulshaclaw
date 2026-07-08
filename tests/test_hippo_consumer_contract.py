"""operator-shell spec：主 repo runtime import 面只能碰 shell / cortex shim。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_import_surface.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_import_surface", CHECKER_PATH)
    assert spec is not None and spec.loader is not None, "scripts/check_import_surface.py should exist"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_repo_import_surface_matches_operator_shell_contract():
    checker = _load_checker()
    offenders = checker.scan_repo(REPO_ROOT)
    assert offenders == []


def test_legacy_memory_and_lifecycle_modules_gone():
    assert not (REPO_ROOT / "paulshaclaw" / "memory").exists()
    assert not (REPO_ROOT / "paulshaclaw" / "lifecycle").exists()
