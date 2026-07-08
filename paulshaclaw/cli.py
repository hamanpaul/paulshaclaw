from __future__ import annotations

import importlib.util
import sys
from typing import Sequence

_USAGE = "usage: psc {coordinator|deck|monitor} <args...>\n"
_MEMORY_MOVED = (
    "psc memory 已遷移至 paulsha-hippo（#125 Phase 1）。\n"
    "改用：hippo <subcommand>（安裝：pipx install git+https://github.com/hamanpaul/paulsha-hippo）\n"
)
_CORTEX_MOVED = (
    "psc {sub} 已遷移至 paulsha-cortex。\n"
    "改用：cortex {sub} <args...>（安裝：pipx install git+https://github.com/hamanpaul/paulsha-cortex）\n"
)
_CORTEX_SUBS = {"coordinator", "deck", "monitor"}


def _has_cortex_cli() -> bool:
    try:
        return importlib.util.find_spec("paulsha_cortex.cli") is not None
    except ModuleNotFoundError:
        return False


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(_USAGE)
        return 2

    head, rest = args[0], args[1:]
    if head == "memory":
        sys.stderr.write(_MEMORY_MOVED)
        return 2
    if head in _CORTEX_SUBS:
        if not _has_cortex_cli():
            sys.stderr.write(_CORTEX_MOVED.format(sub=head))
            return 2
        from paulsha_cortex.cli import main as cortex_main

        forwarded = rest if head == "coordinator" else [head, *rest]
        return int(cortex_main(forwarded) or 0)

    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
