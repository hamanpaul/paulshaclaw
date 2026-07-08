#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

ALLOWED_CORTEX_IMPORTS = frozenset(
    {
        "paulsha_cortex.control.client",
        "paulsha_cortex.cli",
    }
)
BANNED_REPO_SURFACES = frozenset({"persona", "coordinator", "control", "deck", "monitor"})
SCAN_ROOTS = ("paulshaclaw", "scripts")


def _legacy_surface(name: str) -> str | None:
    if not name.startswith("paulshaclaw."):
        return None
    parts = name.split(".")
    if len(parts) < 2:
        return None
    surface = parts[1]
    return surface if surface in BANNED_REPO_SURFACES else None


def _check_absolute_import(name: str, rel_path: Path, lineno: int) -> list[str]:
    offenders: list[str] = []
    if name.startswith("paulsha_cortex") and name not in ALLOWED_CORTEX_IMPORTS:
        offenders.append(f"{rel_path}:{lineno}: disallowed paulsha_cortex import {name}")
    if name.startswith("paulsha_hippo"):
        offenders.append(f"{rel_path}:{lineno}: runtime paulsha_hippo import {name}")
    surface = _legacy_surface(name)
    if surface is not None:
        offenders.append(f"{rel_path}:{lineno}: legacy repo surface import {name}")
    return offenders


def _relative_surface(node: ast.ImportFrom) -> str | None:
    candidates: list[str] = []
    if node.module:
        candidates.append(node.module.split(".", 1)[0])
    candidates.extend(alias.name.split(".", 1)[0] for alias in node.names)
    for candidate in candidates:
        if candidate in BANNED_REPO_SURFACES:
            return candidate
    return None


def scan_file(path: Path, repo_root: Path) -> list[str]:
    rel_path = path.relative_to(repo_root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel_path))
    except SyntaxError as exc:
        lineno = exc.lineno or 1
        return [f"{rel_path}:{lineno}: syntax error: {exc.msg}"]

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                offenders.extend(_check_absolute_import(alias.name, rel_path, node.lineno))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level > 0:
            surface = _relative_surface(node)
            if surface is not None:
                offenders.append(
                    f"{rel_path}:{node.lineno}: relative import of migrated surface {surface}"
                )
            continue
        if node.module:
            offenders.extend(_check_absolute_import(node.module, rel_path, node.lineno))
    return offenders


def scan_repo(repo_root: Path) -> list[str]:
    offenders: list[str] = []
    for root_name in SCAN_ROOTS:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            offenders.extend(scan_file(path, repo_root))
    return offenders


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1]
    offenders = scan_repo(repo_root)
    if offenders:
        sys.stderr.write("\n".join(offenders) + "\n")
        return 1
    print("import surface OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
