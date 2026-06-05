from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from ..importer.project_resolver import resolve_project
from .builder import build_brief


def run(args: argparse.Namespace) -> int:
    # Resolve project: explicit project first, else resolve from cwd+memory_root, else _unknown
    project = getattr(args, "project", None)
    if not project:
        cwd = getattr(args, "cwd", None)
        memory_root = getattr(args, "memory_root", None)
        if cwd:
            project = resolve_project(cwd=cwd, memory_root=memory_root)
        else:
            project = "_unknown"

    # call build_brief
    brief = build_brief(Path(getattr(args, "memory_root")), project, now=getattr(args, "now", None), k=getattr(args, "k", 8), char_budget=getattr(args, "char_budget", 8000))
    if brief:
        print(brief)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="psc memory wakeup")
    parser.add_argument("--memory-root", required=True)
    parser.add_argument("--project", default=None)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--char-budget", type=int, default=8000)
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)
    return run(args)
