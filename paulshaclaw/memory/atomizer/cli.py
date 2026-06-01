from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config as atomizer_config
from . import pipeline


def run(args: argparse.Namespace) -> int:
    override = args.override if getattr(args, "override", None) else atomizer_config._DEFAULT_SENTINEL
    config, config_hash = atomizer_config.load_config(override_path=override)
    result = pipeline.run(
        Path(args.memory_root),
        config=config,
        config_hash=config_hash,
        now=args.now,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0
