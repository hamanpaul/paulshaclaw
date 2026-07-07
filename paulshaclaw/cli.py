from __future__ import annotations

import sys
from typing import Sequence

_USAGE = "usage: psc {coordinator|deck} <args...>\n"
_MEMORY_MOVED = (
    "psc memory 已遷移至 paulsha-hippo（#125 Phase 1）。\n"
    "改用：hippo <subcommand>（安裝：pipx install git+https://github.com/hamanpaul/paulsha-hippo）\n"
)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(_USAGE)
        return 2

    head, rest = args[0], args[1:]
    if head == "memory":
        sys.stderr.write(_MEMORY_MOVED)
        return 2
    if head == "coordinator":
        from paulshaclaw.coordinator.cli import main as coordinator_main

        return int(coordinator_main(rest) or 0)
    if head == "deck":
        from paulshaclaw.deck.cli import main as deck_main

        return int(deck_main(rest) or 0)

    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
