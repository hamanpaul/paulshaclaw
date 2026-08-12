"""launcher.cli（`paulshaclaw` console script）與邊界測試（#288 A 節）。"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from paulshaclaw import launcher
from paulshaclaw.launcher import cli, lock

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_DIR = REPO_ROOT / "paulshaclaw" / "launcher"


def test_package_version_is_available_and_non_empty() -> None:
    # release-contract §6 需要可查版本字串：由 launcher 套件提供
    # （importlib.metadata；未安裝的原始碼樹直跑 fallback "0+unknown"）。
    assert isinstance(launcher.__version__, str)
    assert launcher.__version__


def test_pyproject_declares_both_entry_points() -> None:
    payload = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = payload["project"]["scripts"]
    assert scripts["paulshaclaw"] == "paulshaclaw.launcher.cli:main"
    assert scripts["psc"] == "paulshaclaw.cli:main"
    # 兩個入口語意不同（正式啟動 vs cortex dispatcher），必須並存且互異。
    assert scripts["paulshaclaw"] != scripts["psc"]


def test_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "up" in out and "down" in out and "status" in out


def test_status_outputs_json_shape(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PSC_START_LOCK", str(tmp_path / "start.lock"))
    # 空 PATH → systemctl 不可用，unit 狀態回 unavailable（不打真 systemd）。
    monkeypatch.setenv("PATH", str(tmp_path))

    rc = cli.main(["status"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"version", "lock", "units"}
    assert payload["lock"]["held"] is False
    assert payload["units"] == {
        "paulshaclaw-cost.service": "unavailable",
        "paulshaclaw-telegram.service": "unavailable",
    }


def test_down_goes_through_takeover_path(monkeypatch, capsys) -> None:
    report = {"status": "taken-over", "holder": {"holder": "dev"}}
    monkeypatch.setattr(cli.lock_mod, "takeover", lambda: report)

    rc = cli.main(["down"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == report


def test_down_fails_closed_on_takeover_error(monkeypatch, capsys) -> None:
    def boom() -> dict:
        raise lock.TakeoverError("停不掉")

    monkeypatch.setattr(cli.lock_mod, "takeover", boom)

    rc = cli.main(["down"])

    assert rc == 1
    assert "down failed" in capsys.readouterr().err


def test_launcher_sources_do_not_reference_repo_worktree() -> None:
    """版本 pin：launcher 不讀 repo 工作樹、不注入 module 搜尋路徑覆寫。"""
    banned = ("PYTHON" + "PATH", "PSC_REPO" + "_ROOT")
    for source in sorted(LAUNCHER_DIR.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{source.name} 不得引用 {token}"
