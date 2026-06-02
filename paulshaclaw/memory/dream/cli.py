from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..atomizer import cli as atomizer_cli
from ..atomizer import config as atomizer_config
from ..atomizer import pipeline as atomizer_pipeline
from ..janitor import config as janitor_config
from ..janitor import scanner as janitor_scanner
from ..ledger import dream as dream_ledger
from . import idle, orchestrator


def _run(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)

    if args.require_idle and not idle.is_idle(max_load=args.max_load):
        print(
            json.dumps(
                {
                    "skipped": "system busy",
                    "backlog_depth": dream_ledger.backlog_depth(memory_root),
                },
                sort_keys=True,
            )
        )
        return 0

    atom_cfg, atom_hash = atomizer_config.load_config(override_path=None)
    jan_cfg, jan_hash = janitor_config.load_config(override_path=None)
    promoter = atomizer_cli._build_promoter(args, atom_cfg, memory_root)
    now = args.now

    def atomize_fn() -> dict[str, object]:
        return atomizer_pipeline.run(
            memory_root,
            config=atom_cfg,
            config_hash=atom_hash,
            now=now,
            dry_run=args.dry_run,
            promoter=promoter,
        )

    def janitor_fn() -> dict[str, object]:
        return janitor_scanner.run_scan(
            memory_root=memory_root,
            knowledge_root=memory_root / "knowledge",
            config=jan_cfg,
            config_hash=jan_hash,
            now=now,
            dry_run=args.dry_run,
        )

    result = orchestrator.run_dream(
        memory_root,
        atomize_fn=atomize_fn,
        janitor_fn=janitor_fn,
        now=now,
        config_hash=f"{atom_hash[:8]}:{jan_hash[:8]}",
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def _status(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)
    print(
        json.dumps(
            {
                "last_run": dream_ledger.last_run(memory_root),
                "backlog_depth": dream_ledger.backlog_depth(memory_root),
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def run(args: argparse.Namespace) -> int:
    if args.dream_command == "status":
        return _status(args)
    return _run(args)
