from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bundle, selector


def run(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)
    tags = args.tag or None

    try:
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
    except selector.SelectorError as exc:
        print(f"selector error: {exc}", file=sys.stderr)
        return 2
    except bundle.BundleError as exc:
        print(f"bundle error: {exc}", file=sys.stderr)
        return 2

    print(str(out))
    return 0
