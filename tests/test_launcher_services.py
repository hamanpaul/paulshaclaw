"""launcher.services 單元測試（#288 B 節，方案 2：指令自承 loop）。"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from paulshaclaw.launcher import services


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0)


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


# ---------------------------------------------------------------------------
# cost loop
# ---------------------------------------------------------------------------


def test_cost_loop_runs_module_once_with_config_interval(tmp_path, monkeypatch) -> None:
    config = tmp_path / "paulshaclaw.yaml"
    config.write_text("cost:\n  tmux_refresh_seconds: 7\n", encoding="utf-8")
    monkeypatch.setenv("PAULSHACLAW_CONFIG", str(config))
    monkeypatch.delenv("PSC_COST_REFRESH_DISABLED", raising=False)
    runner = RecordingRunner()
    sleeper = RecordingSleeper()

    rc = services.run_cost_loop(runner=runner, sleeper=sleeper, iterations=2)

    assert rc == 0
    assert runner.calls == [
        [sys.executable, "-m", "paulshaclaw.cost", "--once"],
        [sys.executable, "-m", "paulshaclaw.cost", "--once"],
    ]
    # interval 來源與 service-cost.sh 相同：cost config 的 tmux_refresh_seconds。
    assert sleeper.delays == [7]


def test_cost_loop_skips_when_disabled(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PSC_COST_REFRESH_DISABLED", "1")
    runner = RecordingRunner()

    rc = services.run_cost_loop(runner=runner, iterations=1)

    assert rc == 0
    assert runner.calls == []
    assert "PSC_COST_REFRESH_DISABLED=1" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# telegram（ready-gate 與 backoff）
# ---------------------------------------------------------------------------


def _spawn_fake_listener(code: str):
    def spawn(_cmd, env):
        return subprocess.Popen([sys.executable, "-c", code], env=env)

    return spawn


def test_telegram_ready_gate_passes_when_listener_writes_ready(
    tmp_path, monkeypatch
) -> None:
    ready = tmp_path / "telegram.ready"
    monkeypatch.setenv("PSC_TELEGRAM_READY_FILE", str(ready))
    monkeypatch.setenv("PSC_TELEGRAM_STARTUP_TIMEOUT", "10")
    code = (
        "import os, pathlib, time\n"
        "pathlib.Path(os.environ['PSC_TELEGRAM_READY_FILE']).write_text('ready')\n"
        "time.sleep(0.1)\n"
    )

    rc = services.run_telegram(spawn=_spawn_fake_listener(code), max_spawns=1)

    assert rc == 0


def test_telegram_ready_gate_times_out_when_listener_never_ready(
    tmp_path, monkeypatch, capsys
) -> None:
    ready = tmp_path / "telegram.ready"
    monkeypatch.setenv("PSC_TELEGRAM_READY_FILE", str(ready))
    monkeypatch.setenv("PSC_TELEGRAM_STARTUP_TIMEOUT", "1")
    code = "import time\ntime.sleep(60)\n"

    started = time.monotonic()
    rc = services.run_telegram(
        spawn=_spawn_fake_listener(code), sleeper=time.sleep, max_spawns=1
    )

    assert rc != 0
    assert time.monotonic() - started < 30  # 逾時後 listener 被 TERM，不會等 60s
    assert "readiness timeout" in capsys.readouterr().err


def test_telegram_respawn_backoff_caps_at_120(tmp_path, monkeypatch) -> None:
    ready = tmp_path / "telegram.ready"
    monkeypatch.setenv("PSC_TELEGRAM_READY_FILE", str(ready))
    monkeypatch.setenv("PSC_TELEGRAM_STARTUP_TIMEOUT", "10")
    monkeypatch.setenv("PSC_BOT_BACKOFF_BASE", "5")
    sleeper = RecordingSleeper()
    # listener 立刻非零退出 → 每次 spawn 都算失敗。
    code = "raise SystemExit(1)\n"

    rc = services.run_telegram(
        spawn=_spawn_fake_listener(code), sleeper=sleeper, max_spawns=4
    )

    assert rc != 0
    backoffs = [delay for delay in sleeper.delays if delay >= 1]
    # base 5 → ×6=30 → ×6=180 封頂 120（鏡射 start.sh start_bot_supervised）。
    assert backoffs == [5, 30, 120]


# ---------------------------------------------------------------------------
# dream
# ---------------------------------------------------------------------------


def test_dream_skips_with_warning_when_no_hippo(monkeypatch, capsys) -> None:
    monkeypatch.setenv("HIPPO_BIN", "disabled")
    monkeypatch.setattr(services.importlib.util, "find_spec", lambda _name: None)
    runner = RecordingRunner()

    rc = services.run_dream_loop(runner=runner, iterations=1)

    assert rc == 0
    assert runner.calls == []
    assert "paulsha-hippo 未安裝" in capsys.readouterr().err


def test_dream_uses_hippo_supervise_when_binary_present(tmp_path, monkeypatch) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    monkeypatch.setenv("HIPPO_BIN", "/fake/hippo")
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("PSC_DREAM_INTERVAL_SECONDS", "123")
    runner = RecordingRunner()

    rc = services.run_dream_loop(runner=runner)

    assert rc == 0
    assert runner.calls == [
        [
            "/fake/hippo",
            "dream",
            "supervise",
            "--interval",
            "123",
            "--memory-root",
            str(memory_root),
        ]
    ]


def test_dream_skips_when_memory_root_missing(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HIPPO_BIN", "/fake/hippo")
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(tmp_path / "nope"))
    runner = RecordingRunner()

    rc = services.run_dream_loop(runner=runner)

    assert rc == 0
    assert runner.calls == []
    assert "memory root not found" in capsys.readouterr().err


def test_dream_module_loop_defers_first_run_by_one_interval(
    tmp_path, monkeypatch
) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    monkeypatch.delenv("HIPPO_BIN", raising=False)
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("PSC_DREAM_INTERVAL_SECONDS", "42")
    monkeypatch.setattr(services.shutil, "which", lambda _name: None)
    runner = RecordingRunner()
    sleeper = RecordingSleeper()

    rc = services.run_dream_loop(runner=runner, sleeper=sleeper, iterations=1)

    assert rc == 0
    assert sleeper.delays == [42]  # 首輪延後一個 interval
    assert len(runner.calls) == 1
    cmd = runner.calls[0]
    assert cmd[:5] == [sys.executable, "-m", "paulsha_hippo.cli", "dream", "run"]
    assert "--require-idle" in cmd
    assert "--instruction-root" in cmd


# ---------------------------------------------------------------------------
# main 分派
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "target"),
    [
        ("cost", "run_cost_loop"),
        ("telegram", "run_telegram"),
        ("dream", "run_dream_loop"),
    ],
)
def test_main_dispatches_roles(monkeypatch, role, target) -> None:
    sentinel = {"called": False}

    def fake(**_kwargs):
        sentinel["called"] = True
        return 0

    monkeypatch.setattr(services, target, fake)
    assert services.main([role]) == 0
    assert sentinel["called"] is True


def test_main_rejects_unknown_role() -> None:
    with pytest.raises(SystemExit) as excinfo:
        services.main(["cockpit"])
    assert excinfo.value.code == 2
