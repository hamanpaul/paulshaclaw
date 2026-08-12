"""start lock 雙路徑共用互斥核心（#288 C 節）。

兩條啟動路徑（dev `scripts/start.sh`、release `paulshaclaw`）共用同一把
start lock，裁決為「後起的為主」：新啟動方接管（停掉）既有持有者後才啟動，
停不掉即 fail-closed。

設計要點：
- **flock 為活性真相**：kernel flock 才代表「有人活著持有」；檔內 metadata
  只用於辨識持有者身分與停法。crash 留下的陳舊檔案，flock 會正確判為 free，
  stale metadata 可安全忽略。
- **metadata schema v1**（檔內單行 JSON）::

      {"schema": 1, "holder": "dev"|"release", "pid": ..., "pgid": ...,
       "stop": {"kind": "process", "pid": ...} | {"kind": "systemd", "unit": ...},
       "version": "0.1.0"|"dev@<repo>", "started_at": "..."}

- **停法由 metadata 的 stop.kind 決定**：process 持有者送 SIGTERM；systemd
  持有者必須走 `systemctl --user stop`（直接 kill 會被 Restart=on-failure
  拉回來，造成兩套並存的假象循環）。
- **三平面邊界**：接管只停操作面自己的行程與 units（`<operator-instance>-cost`
  / `-telegram`），絕不觸碰 cortex / hippo 的 systemd 常駐服務。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

SCHEMA_VERSION = 1
LOCK_FILENAME = "paulshaclaw-start.lock"
DEFAULT_TAKEOVER_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.2

# 治理／記憶平面的字樣白名單防線：任何 stop 目標命中即屬越界，fail-closed。
_FORBIDDEN_UNIT_MARKERS = ("manager", "monitor")
_FORBIDDEN_UNIT_PREFIXES = ("cortex-", "hippo-")

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


class TakeoverError(RuntimeError):
    """接管失敗（含停不掉、metadata 無法解讀）——呼叫端必須 fail-closed 不啟動。"""

    def __init__(self, message: str, *, holder: dict | None = None) -> None:
        super().__init__(message)
        self.holder = holder


class LockHeldError(RuntimeError):
    """flock 已被他人持有。"""


def operator_instance() -> str:
    """操作面 instance 名（unit 前綴）。

    刻意獨立於 PSC_INSTANCE（start.sh 內該變數語意是 cortex instance、預設
    cortex）——誤用會把治理面 units 納入 stop 清單。
    """
    return os.environ.get("PSC_OPERATOR_INSTANCE", "").strip() or "paulshaclaw"


def default_lock_path() -> Path:
    """lock 檔路徑：PSC_START_LOCK > XDG_RUNTIME_DIR > /run/user/<uid> > /tmp。

    鏡射 start.sh ensure_xdg_runtime_dir 的規則：XDG_RUNTIME_DIR 未設但
    /run/user/<uid> 存在且可寫時視同已設，避免同一台機器出現兩個 lock 路徑。
    """
    override = os.environ.get("PSC_START_LOCK", "").strip()
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if xdg:
        return Path(xdg) / LOCK_FILENAME
    candidate = Path(f"/run/user/{os.getuid()}")
    if candidate.is_dir() and os.access(candidate, os.W_OK):
        return candidate / LOCK_FILENAME
    return Path("/tmp") / LOCK_FILENAME


def build_holder_meta(
    *,
    holder: str,
    pid: int,
    stop: dict,
    version: str,
) -> dict:
    try:
        pgid: int | None = os.getpgid(pid)
    except OSError:
        pgid = None
    return {
        "schema": SCHEMA_VERSION,
        "holder": holder,
        "pid": pid,
        "pgid": pgid,
        "stop": stop,
        "version": version,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def read_holder(path: Path | str) -> dict | None:
    """讀 lock 檔 metadata；空檔／不可讀／非 JSON 皆回 None（由呼叫端裁決）。"""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        payload = json.loads(text.splitlines()[0])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def write_holder(path: Path | str, meta: dict) -> None:
    """由路徑截斷重寫 metadata（單行 JSON）。

    只能在 flock 已在手上時呼叫：flock 綁 inode，經路徑重新開檔截斷不會影響
    既有鎖；但若鎖不在手上，這一寫會截毀真正持有者的 metadata。
    """
    Path(path).write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")


class HeldLock:
    """flock 持有物：取得後由路徑截斷重寫 metadata，fd 持有至行程結束。"""

    def __init__(self, path: Path | str, meta: dict) -> None:
        self.path = Path(path)
        self.meta = meta
        self._fd: int | None = None

    def acquire(self) -> None:
        # O_RDWR|O_CREAT「不截斷」：截斷要等鎖到手，否則會毀掉現任持有者 metadata。
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise LockHeldError(f"start lock 已被持有：{self.path}") from exc
        self._fd = fd
        write_holder(self.path, self.meta)

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> "HeldLock":
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _probe_free(path: Path) -> bool:
    """flock 探測：能取得（隨即釋放）即 free。"""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    finally:
        os.close(fd)
    return True


def _default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=False, capture_output=True, text=True)


def _guard_unit(unit: str) -> None:
    if any(marker in unit for marker in _FORBIDDEN_UNIT_MARKERS) or unit.startswith(
        _FORBIDDEN_UNIT_PREFIXES
    ):
        raise TakeoverError(
            f"stop 目標 {unit!r} 疑似治理／記憶平面 unit——接管邊界僅及操作面，fail-closed"
        )


def operator_unit_names(instance: str | None = None) -> list[str]:
    """接管時允許停用的操作面 units（白名單建構）。"""
    inst = instance or operator_instance()
    units = [f"{inst}-cost.service", f"{inst}-telegram.service"]
    for unit in units:
        _guard_unit(unit)
    return units


def stop_operator_units(
    instance: str | None = None, runner: Runner | None = None
) -> list[str]:
    """僅停操作面自己的 units；systemctl 不可用即 skip。"""
    units = operator_unit_names(instance)
    if runner is None:
        if shutil.which("systemctl") is None:
            return []
        runner = _default_runner
    actions: list[str] = []
    for unit in units:
        completed = runner(["systemctl", "--user", "stop", unit])
        actions.append(f"systemctl --user stop {unit} -> rc={completed.returncode}")
    return actions


def _resolve_timeout(timeout: float | None) -> float:
    if timeout is not None:
        return float(timeout)
    raw = os.environ.get("PSC_TAKEOVER_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_TAKEOVER_TIMEOUT_SECONDS


def _stop_holder(holder: dict, runner: Runner) -> str:
    stop = holder.get("stop")
    if not isinstance(stop, dict):
        raise TakeoverError(
            "持有者 metadata 缺 stop 欄位——無從安全停用，fail-closed", holder=holder
        )
    kind = stop.get("kind")
    if kind == "process":
        pid = stop.get("pid")
        if not isinstance(pid, int) or pid <= 1:
            raise TakeoverError(
                f"process 持有者 pid 無效（{pid!r}），fail-closed", holder=holder
            )
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # 已消失；由後續 flock 輪詢確認釋放
        except PermissionError as exc:
            raise TakeoverError(
                f"無權停用持有者 pid={pid}，fail-closed", holder=holder
            ) from exc
        return f"SIGTERM pid={pid}"
    if kind == "systemd":
        unit = stop.get("unit")
        if not isinstance(unit, str) or not unit:
            raise TakeoverError(
                "systemd 持有者缺 unit 名稱，fail-closed", holder=holder
            )
        _guard_unit(unit)
        try:
            completed = runner(["systemctl", "--user", "stop", unit])
        except FileNotFoundError as exc:
            raise TakeoverError(
                f"systemctl 不可用，無法停用 systemd 持有者 {unit}，fail-closed",
                holder=holder,
            ) from exc
        if completed.returncode != 0:
            raise TakeoverError(
                f"systemctl --user stop {unit} 失敗（rc={completed.returncode}）",
                holder=holder,
            )
        return f"systemctl --user stop {unit}"
    raise TakeoverError(
        f"未知的 stop.kind={kind!r}——無從安全停用，fail-closed", holder=holder
    )


def takeover(
    path: Path | str | None = None,
    *,
    timeout: float | None = None,
    instance: str | None = None,
    runner: Runner | None = None,
) -> dict:
    """「後起的為主」接管：停操作面 units → 停 flock 持有者 → 輪詢至釋放。

    停不掉（逾時／metadata 無法解讀／越界 stop 目標）一律拋 `TakeoverError`
    fail-closed——絕不盲殺、絕不兩套並存。回傳 report（dict）供呼叫端記錄。
    """
    lock_path = Path(path) if path is not None else default_lock_path()
    effective_runner = runner or _default_runner
    report: dict = {
        "lock": str(lock_path),
        "stopped_units": stop_operator_units(instance, runner),
        "holder": None,
        "stop_action": None,
    }
    if _probe_free(lock_path):
        report["status"] = "free"
        return report

    holder = read_holder(lock_path)
    if holder is None:
        raise TakeoverError(
            f"start lock 被持有但 metadata 無法解讀（{lock_path}）——"
            "不盲殺，fail-closed；請人工確認持有者後再啟動"
        )
    report["holder"] = holder
    report["stop_action"] = _stop_holder(holder, effective_runner)

    deadline = time.monotonic() + _resolve_timeout(timeout)
    while time.monotonic() < deadline:
        if _probe_free(lock_path):
            report["status"] = "taken-over"
            return report
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise TakeoverError(
        "接管逾時：既有持有者仍未釋放 start lock，fail-closed 不啟動。"
        f"持有者：{json.dumps(holder, ensure_ascii=False)}",
        holder=holder,
    )


def status(path: Path | str | None = None) -> dict:
    lock_path = Path(path) if path is not None else default_lock_path()
    free = _probe_free(lock_path)
    return {
        "lock": str(lock_path),
        "held": not free,
        "holder": None if free else read_holder(lock_path),
    }


# ---------------------------------------------------------------------------
# CLI：`python -m paulshaclaw.launcher.lock ...`（start.sh 消費）
# ---------------------------------------------------------------------------


def _dev_version(source: str | None) -> str:
    return f"dev@{source}" if source else "dev"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paulshaclaw.launcher.lock")
    sub = parser.add_subparsers(dest="command", required=True)

    p_takeover = sub.add_parser("takeover", help="接管既有持有者（後起的為主）")
    p_takeover.add_argument("--lock-file", default=None)
    p_takeover.add_argument("--timeout", type=float, default=None)
    p_takeover.add_argument("--instance", default=None)

    p_write = sub.add_parser("write-holder", help="flock 已在手上時重寫 metadata")
    p_write.add_argument("--lock-file", required=True)
    p_write.add_argument("--holder", required=True, choices=("dev", "release"))
    p_write.add_argument("--pid", type=int, required=True)
    p_write.add_argument("--source", default=None, help="dev 持有者的 repo 路徑（記錄用）")

    p_status = sub.add_parser("status", help="印出 lock 持有狀態 JSON")
    p_status.add_argument("--lock-file", default=None)

    sub.add_parser("path", help="印出預設 lock 檔路徑")

    args = parser.parse_args(argv)

    if args.command == "takeover":
        try:
            report = takeover(
                args.lock_file, timeout=args.timeout, instance=args.instance
            )
        except TakeoverError as exc:
            print(f"takeover failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False))
        return 0

    if args.command == "write-holder":
        if args.holder == "release":
            from . import __version__ as version
        else:
            version = _dev_version(args.source)
        meta = build_holder_meta(
            holder=args.holder,
            pid=args.pid,
            stop={"kind": "process", "pid": args.pid},
            version=version,
        )
        write_holder(args.lock_file, meta)
        return 0

    if args.command == "status":
        print(json.dumps(status(args.lock_file), ensure_ascii=False))
        return 0

    if args.command == "path":
        print(default_lock_path())
        return 0

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
