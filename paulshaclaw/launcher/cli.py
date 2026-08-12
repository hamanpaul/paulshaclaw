"""`paulshaclaw` console script 入口（#288 A 節）。

- `paulshaclaw`／`paulshaclaw up`：正式啟動 operator shell（前景 supervisor）。
- `paulshaclaw down`：接管（停掉）現任持有者後不啟動，回報結果。
- `paulshaclaw status`：印 lock holder metadata 與操作面 unit 狀態 JSON。

與 `psc`（paulshaclaw.cli，cortex dispatcher）語意分離：本入口不轉發任何
cortex 子命令、不 import paulshaclaw.cli。執行期鎖定自身安裝版本，全程不讀
repo 工作樹。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import Sequence

from paulshaclaw import __version__

from . import lock as lock_mod


def _unit_states() -> dict[str, str]:
    units = lock_mod.operator_unit_names()
    if shutil.which("systemctl") is None:
        return {unit: "unavailable" for unit in units}
    states: dict[str, str] = {}
    for unit in units:
        completed = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            check=False,
            capture_output=True,
            text=True,
        )
        states[unit] = completed.stdout.strip() or "unknown"
    return states


def _cmd_up(no_cockpit: bool) -> int:
    from .supervisor import run

    return run(no_cockpit=no_cockpit)


def _cmd_down() -> int:
    try:
        report = lock_mod.takeover()
    except lock_mod.TakeoverError as exc:
        print(f"down failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


def _cmd_status() -> int:
    payload = {
        "version": __version__,
        "lock": lock_mod.status(),
        "units": _unit_states(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="paulshaclaw",
        description="paulshaclaw operator shell 正式啟動入口（release 路徑；dev 路徑為 scripts/start.sh）",
    )
    parser.add_argument(
        "--version", action="version", version=f"paulshaclaw {__version__}"
    )
    sub = parser.add_subparsers(dest="command")
    p_up = sub.add_parser("up", help="啟動 operator shell（預設子命令）")
    p_up.add_argument(
        "--no-cockpit",
        action="store_true",
        help="不起 cockpit TUI，常駐前景（無 tmux 環境用）",
    )
    sub.add_parser("down", help="停掉現任 operator shell（不啟動新的）")
    sub.add_parser("status", help="印出 start lock 與操作面 unit 狀態")

    args = parser.parse_args(argv)
    command = args.command or "up"
    if command == "up":
        return _cmd_up(getattr(args, "no_cockpit", False))
    if command == "down":
        return _cmd_down()
    if command == "status":
        return _cmd_status()
    parser.error(f"unknown command {command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
