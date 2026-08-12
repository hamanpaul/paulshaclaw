"""service loop 的 Python 權威實作（#288 B 節，裁決＝方案 2）。

release 路徑不依賴 repo `scripts/service-*.sh`：systemd unit 模板的 ExecStart
直指 `__PYTHON__ -m paulshaclaw.launcher.services <role>`（render 時代入安裝
venv 的直譯器），supervisor 亦重用同組 loop。

版本 pin 原則：所有 spawn 一律用 `sys.executable`、不注入任何 module 搜尋路徑
覆寫——只用安裝 venv 內的套件，不讀 repo 工作樹。

行為鏡射來源（dev 路徑為既有真相）：
- cost：scripts/service-cost.sh（interval 取 cost config 的 tmux_refresh_seconds）
- telegram：scripts/start.sh start_bot_supervised ＋ scripts/service-bot.sh
  的 ready-gate／respawn backoff
- dream：scripts/service-dream.sh（hippo 偵測順序 HIPPO_BIN > PATH > module）
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from paulshaclaw.config import paths

Runner = Callable[[Sequence[str]], object]

_TERMINATED = False


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw.isdigit():
        return int(raw)
    return default


def _install_sigterm_handler() -> None:
    def _handle(signum: int, _frame: object) -> None:
        global _TERMINATED
        _TERMINATED = True
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def _terminate_child(child: subprocess.Popen) -> None:
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def _default_runner(cmd: Sequence[str]) -> object:
    return subprocess.run(list(cmd), check=False)


# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------


def cost_interval_seconds() -> int:
    """interval 來源與 service-cost.sh 相同：cost config 的 tmux_refresh_seconds。"""
    try:
        from paulshaclaw.cost.config import load_cost_config

        config_path = os.environ.get("PAULSHACLAW_CONFIG", "").strip()
        config = load_cost_config(config_path=Path(config_path) if config_path else None)
        interval = int(config.tmux_refresh_seconds)
    except Exception:
        interval = 30
    if interval <= 0:
        interval = 30
    return interval


def run_cost_loop(
    *,
    runner: Runner | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    iterations: int | None = None,
) -> int:
    if os.environ.get("PSC_COST_REFRESH_DISABLED", "0") == "1":
        print("cost refresh loop disabled (PSC_COST_REFRESH_DISABLED=1)")
        return 0
    interval = cost_interval_seconds()
    effective_runner = runner or _default_runner
    count = 0
    while not _TERMINATED:
        effective_runner([sys.executable, "-m", "paulshaclaw.cost", "--once"])
        count += 1
        if iterations is not None and count >= iterations:
            return 0
        sleeper(interval)
    return 0


# ---------------------------------------------------------------------------
# telegram
# ---------------------------------------------------------------------------


def _telegram_ready_file() -> Path:
    override = os.environ.get("PSC_TELEGRAM_READY_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return paths.run_root() / "telegram.ready"


def _default_spawn(cmd: Sequence[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(list(cmd), env=env)


def run_telegram(
    *,
    spawn: Callable[[Sequence[str], dict[str, str]], subprocess.Popen] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    max_spawns: int | None = None,
) -> int:
    """listener 常駐 supervise：ready-gate ＋ respawn backoff。

    鏡射語意：ready file 逾時未寫（PSC_TELEGRAM_STARTUP_TIMEOUT，預設 40s）
    或 listener 非零退出＝失敗，backoff 後 respawn（base PSC_BOT_BACKOFF_BASE
    預設 5s、×6、封頂 120s）；listener 乾淨退出（rc=0）即結束。
    systemd Restart=on-failure 為外層保險。
    """
    ready_file = _telegram_ready_file()
    startup_timeout = _int_env("PSC_TELEGRAM_STARTUP_TIMEOUT", 40)
    delay = _int_env("PSC_BOT_BACKOFF_BASE", 5)
    if delay > 120:
        delay = 120
    effective_spawn = spawn or _default_spawn
    spawns = 0
    last_status = 1
    while not _TERMINATED:
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.write_text("", encoding="utf-8")
        env = os.environ.copy()
        env["PSC_TELEGRAM_READY_FILE"] = str(ready_file)
        child = effective_spawn(
            [sys.executable, "-m", "paulshaclaw.bot.listener"], env
        )
        spawns += 1
        try:
            last_status = _supervise_telegram_child(
                child, ready_file, startup_timeout, sleeper
            )
        except BaseException:
            _terminate_child(child)
            raise
        if last_status == 0:
            return 0
        print(
            f"bot exited unexpectedly (status={last_status}); "
            f"respawn in {delay}s",
            file=sys.stderr,
        )
        if max_spawns is not None and spawns >= max_spawns:
            return last_status
        sleeper(delay)
        delay = min(delay * 6, 120)
    return last_status


def _supervise_telegram_child(
    child: subprocess.Popen,
    ready_file: Path,
    startup_timeout: float,
    sleeper: Callable[[float], None],
) -> int:
    deadline = time.monotonic() + startup_timeout
    while True:
        try:
            if ready_file.stat().st_size > 0:
                break
        except OSError:
            pass
        if child.poll() is not None:
            print("telegram listener exited before ready", file=sys.stderr)
            return child.returncode or 1
        if time.monotonic() >= deadline:
            print("telegram listener readiness timeout", file=sys.stderr)
            _terminate_child(child)
            return 1
        sleeper(0.05)
    return child.wait()


# ---------------------------------------------------------------------------
# dream
# ---------------------------------------------------------------------------

_DREAM_INSTRUCTION_ROOTS = (
    ".claude/CLAUDE.md",
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    ".codex",
    ".agents",
    ".gemini",
    "prj_pri",
)


def _dream_instruction_root_args() -> list[str]:
    home = paths.home_root()
    args: list[str] = []
    for rel in _DREAM_INSTRUCTION_ROOTS:
        args.extend(["--instruction-root", str(home / rel)])
    extra = os.environ.get("PSC_EXTRA_CORPUS_ROOT", "").strip()
    if extra:
        args.extend(["--instruction-root", extra])
    return args


def _resolve_hippo_bin() -> str | None:
    """hippo 偵測順序（鏡射 service-dream.sh）：HIPPO_BIN > PATH > module。"""
    hippo_bin = os.environ.get("HIPPO_BIN", "").strip()
    if hippo_bin == "disabled":
        return None
    if hippo_bin:
        return hippo_bin
    return shutil.which("hippo")


def run_dream_loop(
    *,
    runner: Runner | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    iterations: int | None = None,
) -> int:
    if os.environ.get("PSC_DREAM_DISABLED", "0") == "1":
        print("dream loop disabled (PSC_DREAM_DISABLED=1)")
        return 0
    hippo_bin = _resolve_hippo_bin()
    if hippo_bin is None and importlib.util.find_spec("paulsha_hippo") is None:
        print(
            "dream loop skipped: paulsha-hippo 未安裝"
            "（pipx install git+https://github.com/hamanpaul/paulsha-hippo）",
            file=sys.stderr,
        )
        return 0
    dream_root = paths.memory_root()
    if not dream_root.exists():
        print(f"dream loop skipped: memory root not found ({dream_root})", file=sys.stderr)
        return 0
    interval = _int_env("PSC_DREAM_INTERVAL_SECONDS", 3600)
    effective_runner = runner or _default_runner

    if hippo_bin:
        # hippo binary 可用時交給 hippo 自有 supervise（首輪延後語意相同）。
        effective_runner(
            [
                hippo_bin,
                "dream",
                "supervise",
                "--interval",
                str(interval),
                "--memory-root",
                str(dream_root),
            ]
        )
        return 0

    count = 0
    while not _TERMINATED:
        # 首輪延後一個 interval：開機當下 load 低，idle gate 必過而疊上啟動尖峰。
        sleeper(interval)
        effective_runner(
            [
                sys.executable,
                "-m",
                "paulsha_hippo.cli",
                "dream",
                "run",
                "--memory-root",
                str(dream_root),
                "--require-idle",
                "--promoter",
                "llm",
                *_dream_instruction_root_args(),
            ]
        )
        count += 1
        if iterations is not None and count >= iterations:
            return 0
    return 0


# ---------------------------------------------------------------------------
# main：`python -m paulshaclaw.launcher.services {cost|telegram|dream}`
# ---------------------------------------------------------------------------

_ROLES: dict[str, Callable[[], int]] = {
    "cost": lambda: run_cost_loop(),
    "telegram": lambda: run_telegram(),
    "dream": lambda: run_dream_loop(),
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paulshaclaw.launcher.services")
    parser.add_argument("role", choices=sorted(_ROLES))
    args = parser.parse_args(argv)
    _install_sigterm_handler()
    return _ROLES[args.role]()


if __name__ == "__main__":
    raise SystemExit(main())
