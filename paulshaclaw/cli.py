from __future__ import annotations

import sys
from typing import Sequence

_USAGE = "usage: psc {memory|coordinator|deck} <args...>\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(_USAGE)
        return 2

    head, rest = args[0], args[1:]
    if head == "memory":
        from paulshaclaw.memory.cli import main as memory_main

        return int(memory_main(["memory", *rest]) or 0)
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
