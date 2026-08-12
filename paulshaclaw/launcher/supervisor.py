"""與 scripts/start.sh 對等的前景 supervisor（#288 A 節，release 啟動路徑）。

函式序鏡射 start.sh main（行 297-545）：
ensure_xdg_runtime_dir → lock takeover+acquire → telegram env 預設載入 →
telegram 設定 gate → stage8 footer → cost loop（TMUX 下）→ ensure_cortex
（偵測＋fallback）→ stagger → dream → telegram ready-gate → verify fallback
alive → cockpit → shutdown cleanup。

與 dev 路徑的明確裁決差異：**不跑 `cortex install service`**——該動作綁 repo
checkout（--repo-root），屬治理面部署，release 路徑只做偵測（manager.lock
flock 探測＋monitor pgrep），缺者以本 venv 起 local fallback。

版本 pin：全程使用 `sys.executable` 與安裝 venv 內的套件，不讀 repo 工作樹。
subprocess 預設 close_fds=True，子程序不繼承 lock fd。
"""
from __future__ import annotations

import fcntl
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from paulshaclaw import __version__
from paulshaclaw.config import paths

from . import lock as lock_mod
from .services import cost_interval_seconds


class SupervisorError(RuntimeError):
    """啟動流程 fail-closed 錯誤（訊息不含任何密鑰內容）。"""


def ensure_xdg_runtime_dir() -> None:
    """鏡射 start.sh ensure_xdg_runtime_dir：目錄真的在就補回預設值。"""
    if os.environ.get("XDG_RUNTIME_DIR", "").strip():
        return
    candidate = Path(f"/run/user/{os.getuid()}")
    if candidate.is_dir() and os.access(candidate, os.W_OK):
        os.environ["XDG_RUNTIME_DIR"] = str(candidate)


def load_default_telegram_env() -> None:
    """secret env 與 state config 的 well-known 預設（鏡射 start.sh:318-329）。

    僅在對應 env 未設時填入；secret 值絕不落 log。
    """
    secret_env = paths.config_root() / "paulshaclaw.telegram.secret.env"
    state_config = paths.config_root() / "paulshaclaw.state.json"
    if not os.environ.get("PSC_TELEGRAM_BOT_TOKEN", "") and secret_env.is_file():
        for line in secret_env.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, separator, value = stripped.partition("=")
            if not separator:
                continue
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    if not os.environ.get("PSC_STAGE1_CONFIG", "") and state_config.is_file():
        os.environ["PSC_STAGE1_CONFIG"] = str(state_config)


def telegram_gate() -> bool:
    """token＋config 齊全才啟動；只給一半即 fail（鏡射 start.sh:449-469）。"""
    token_present = bool(os.environ.get("PSC_TELEGRAM_BOT_TOKEN", ""))
    config_value = os.environ.get("PSC_STAGE1_CONFIG", "")
    config_present = bool(config_value)
    config_readable = config_present and os.access(config_value, os.R_OK)
    if not token_present and not config_present:
        print("telegram skipped: missing PSC_TELEGRAM_BOT_TOKEN or PSC_STAGE1_CONFIG")
        return False
    if token_present and config_present and config_readable:
        return True
    raise SupervisorError(
        "telegram startup requires both PSC_TELEGRAM_BOT_TOKEN and readable PSC_STAGE1_CONFIG"
    )


def _tmux(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["tmux", *args], check=False, capture_output=True, text=True
    )


def apply_stage8_footer() -> None:
    """tmux 存在才動；footer cmd 用 sys.executable（鏡射 start.sh:388-441）。"""
    if not os.environ.get("TMUX", ""):
        return
    if shutil.which("tmux") is None:
        return
    footer_env = ""
    config = os.environ.get("PAULSHACLAW_CONFIG", "")
    if config:
        footer_env = f"PAULSHACLAW_CONFIG={config} "
    footer_cmd = f"#({footer_env}{sys.executable} -m paulshaclaw.cost.status --no-refresh)"
    existing_right = _tmux(["show-option", "-qv", "status-right"]).stdout.rstrip("\n")
    refresh_seconds = cost_interval_seconds()

    _tmux(["set-option", "status-interval", str(refresh_seconds)])
    _tmux(["set-option", "status-right-length", "200"])
    if existing_right.startswith(footer_cmd):
        return
    if "paulshaclaw.cost.status" in existing_right:
        updated = re.sub(
            r"#\([^)]*paulshaclaw\.cost\.status[^)]*\)", footer_cmd, existing_right, count=1
        )
        _tmux(["set-option", "status-right", updated])
    elif not existing_right:
        _tmux(["set-option", "status-right", footer_cmd])
    else:
        _tmux(["set-option", "status-right", f"{existing_right} {footer_cmd}"])


def _manager_lock_is_held() -> bool:
    """flock 探測（鏡射 start.sh:151-160）：kernel 鎖狀態才是真相。"""
    manager_lock = paths.control_root() / "manager.lock"
    if not manager_lock.is_file():
        return False
    try:
        fd = os.open(manager_lock, os.O_RDWR)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        os.close(fd)
    return False


def _monitor_is_running() -> bool:
    """pgrep 探測（鏡射 start.sh:163-166）：monitor 無 single-instance 保護。"""
    pattern = os.environ.get("PSC_MONITOR_PROC_PATTERN", "") or "-m paulsha_cortex.monitor"
    completed = subprocess.run(
        ["pgrep", "-f", "--", pattern], check=False, capture_output=True
    )
    return completed.returncode == 0


class Supervisor:
    def __init__(self, *, no_cockpit: bool = False) -> None:
        self.no_cockpit = no_cockpit
        self.children: dict[str, subprocess.Popen] = {}
        self.manager: subprocess.Popen | None = None
        self.held_lock: lock_mod.HeldLock | None = None
        self._shutdown_done = False

    # -- 啟動步驟 -----------------------------------------------------------

    def acquire_start_lock(self) -> None:
        lock_path = lock_mod.default_lock_path()
        lock_mod.takeover(lock_path)  # 停不掉會拋 TakeoverError（fail-closed）
        meta = lock_mod.build_holder_meta(
            holder="release",
            pid=os.getpid(),
            stop={"kind": "process", "pid": os.getpid()},
            version=__version__,
        )
        held = lock_mod.HeldLock(lock_path, meta)
        try:
            held.acquire()
        except lock_mod.LockHeldError as exc:
            raise SupervisorError(
                "接管後仍取不到 start lock（可能有並發啟動），fail-closed"
            ) from exc
        self.held_lock = held

    def _spawn_service(self, name: str, cmd: list[str], *, log_name: str, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
        log_root = paths.log_root()
        log_root.mkdir(parents=True, exist_ok=True)
        log_file = open(log_root / log_name, "ab")
        env = os.environ.copy()
        env.update(extra_env or {})
        try:
            child = subprocess.Popen(
                cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env
            )
        finally:
            log_file.close()
        self.children[name] = child
        return child

    def start_cost_loop(self) -> None:
        # TMUX guard 在呼叫端（鏡射 start.sh:442-446）；systemd 路徑由
        # `-m paulshaclaw.launcher.services cost` 直跑、不受此限。
        if not os.environ.get("TMUX", ""):
            return
        self._spawn_service(
            "cost",
            [sys.executable, "-m", "paulshaclaw.launcher.services", "cost"],
            log_name="cost.log",
        )

    def ensure_cortex(self) -> None:
        """偵測＋fallback（明確裁決差異：release 路徑不跑 cortex install service）。"""
        if os.environ.get("PSC_MANAGER_DISABLED", "0") == "1":
            print("cortex services disabled (PSC_MANAGER_DISABLED=1)")
            return
        specs_root = Path(
            os.environ.get("PSC_MANAGER_SPECS_DIR", "")
            or os.environ.get("PSC_SPECS_ROOT", "")
            or str(paths.specs_root())
        )
        specs_root.mkdir(parents=True, exist_ok=True)

        if _monitor_is_running():
            print("cortex monitor 已在運行，fallback 不重起 monitor", file=sys.stderr)
        else:
            child = self._spawn_service(
                "cortex-monitor",
                [sys.executable, "-m", "paulsha_cortex.cli", "monitor"],
                log_name="cortex-monitor.log",
            )
            if child.poll() is not None:
                raise SupervisorError("cortex fallback monitor exited before startup")

        if _manager_lock_is_held():
            print(
                "cortex manager 已在運行（manager.lock 被持有），fallback 不重起 manager daemon",
                file=sys.stderr,
            )
        else:
            manager = self._spawn_service(
                "cortex-manager",
                [
                    sys.executable,
                    "-m",
                    "paulsha_cortex.coordinator.manager_daemon",
                    "--specs-dir",
                    str(specs_root),
                ],
                log_name="cortex-manager.log",
                extra_env={
                    "PSC_CONTROL_ROOT": os.environ.get("PSC_CONTROL_ROOT", "")
                    or str(paths.control_root())
                },
            )
            self.manager = manager
            self.children.pop("cortex-manager", None)
            if manager.poll() is not None:
                raise SupervisorError(
                    "cortex fallback manager daemon exited before startup"
                )

    def start_dream(self) -> None:
        self._spawn_service(
            "dream",
            [sys.executable, "-m", "paulshaclaw.launcher.services", "dream"],
            log_name="dream.log",
        )

    def start_telegram(self) -> None:
        """spawn telegram loop 並在前景做 ready-gate（鏡射 start.sh:480-521）。"""
        ready_file = paths.run_root() / "telegram.ready"
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.write_text("", encoding="utf-8")
        startup_timeout = float(os.environ.get("PSC_TELEGRAM_STARTUP_TIMEOUT", "") or 40)
        child = self._spawn_service(
            "telegram",
            [sys.executable, "-m", "paulshaclaw.launcher.services", "telegram"],
            log_name="telegram.log",
            extra_env={"PSC_TELEGRAM_READY_FILE": str(ready_file)},
        )
        deadline = time.monotonic() + startup_timeout
        while True:
            try:
                if ready_file.stat().st_size > 0:
                    break
            except OSError:
                pass
            if child.poll() is not None:
                raise SupervisorError("telegram listener exited before ready")
            if time.monotonic() >= deadline:
                raise SupervisorError("telegram listener readiness timeout")
            time.sleep(0.05)
        if child.poll() is not None:
            raise SupervisorError("telegram listener exited after ready")
        print(f"telegram pid={child.pid}")

    def verify_cortex_fallback_alive(self) -> None:
        """cockpit 前最後把關：只檢查本輪 fallback 自己起的（鏡射 start.sh:170-184）。"""
        monitor = self.children.get("cortex-monitor")
        if monitor is not None and monitor.poll() is not None:
            raise SupervisorError("cortex fallback monitor exited before cockpit start")
        if self.manager is not None and self.manager.poll() is not None:
            raise SupervisorError("cortex fallback manager exited before cockpit start")

    def run_cockpit(self) -> int:
        pane = os.environ.get("TMUX_PANE", "")
        if not pane:
            raise SupervisorError(
                "cockpit 需要 tmux（TMUX_PANE 未設）；無 tmux 環境請用 --no-cockpit"
            )
        # 背景起的行程 stdin 預設為 /dev/null，Textual 需要 TTY；先探測 /dev/tty
        #（鏡射 start.sh:534-537），開不了再退回 /dev/null。
        stdin_path = "/dev/null"
        try:
            probe = os.open("/dev/tty", os.O_RDONLY)
            os.close(probe)
            stdin_path = "/dev/tty"
        except OSError:
            pass
        with open(stdin_path, "rb") as stdin_handle:
            cockpit = subprocess.Popen(
                [sys.executable, "-m", "paulshaclaw.cockpit", "--cockpit-pane", pane],
                stdin=stdin_handle,
            )
        self.children["cockpit"] = cockpit
        return cockpit.wait()

    def wait_forever(self) -> int:
        """--no-cockpit：常駐等訊號（供無 tmux 的全新機器驗收）。"""
        try:
            while True:
                signal.pause()
        except KeyboardInterrupt:
            return 130

    # -- 收尾 ---------------------------------------------------------------

    def shutdown(self) -> None:
        """TERM 全部子程序 → wait → manager TERM 後 5s 寬限再 KILL（鏡射 start.sh:342-372）。"""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        for child in self.children.values():
            if child.poll() is None:
                child.terminate()
        for child in self.children.values():
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if self.manager is not None and self.manager.poll() is None:
            self.manager.terminate()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self.manager.poll() is None:
                time.sleep(0.05)
            if self.manager.poll() is None:
                self.manager.kill()
            self.manager.wait()
        if self.held_lock is not None:
            self.held_lock.release()
            self.held_lock = None


def run(*, no_cockpit: bool = False) -> int:
    supervisor = Supervisor(no_cockpit=no_cockpit)

    def _on_term(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_term)

    print(f"paulshaclaw {__version__}（venv: {sys.prefix}）")
    try:
        ensure_xdg_runtime_dir()
        supervisor.acquire_start_lock()
        load_default_telegram_env()
        telegram_enabled = telegram_gate()
        apply_stage8_footer()
        supervisor.start_cost_loop()
        supervisor.ensure_cortex()
        # 錯開啟動尖峰（鏡射 start.sh:473-475）。
        time.sleep(2)
        supervisor.start_dream()
        if telegram_enabled:
            supervisor.start_telegram()
        time.sleep(2)
        supervisor.verify_cortex_fallback_alive()
        if no_cockpit:
            return supervisor.wait_forever()
        return supervisor.run_cockpit()
    except lock_mod.TakeoverError as exc:
        print(f"接管既有 operator shell 失敗（fail-closed，不啟動）：{exc}", file=sys.stderr)
        return 1
    except SupervisorError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return code
    finally:
        supervisor.shutdown()
