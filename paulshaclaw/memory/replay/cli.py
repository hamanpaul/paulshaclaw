from __future__ import annotations

import argparse
from pathlib import Path

from . import bundle, selector


def run(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)
    tags = args.tag or None
    slices = selector.select(
        memory_root,
        project=args.project,
        tags=tags,
        entity=args.entity,
        include_decayed=args.include_decayed,
    )
    selection = {
        "project": args.project,
        "tags": tags,
        "entity": args.entity,
        "include_decayed": args.include_decayed,
    }
    out = bundle.build(memory_root, slices, Path(args.out), selection=selection, now=args.now)
    print(str(out))
    return 0
