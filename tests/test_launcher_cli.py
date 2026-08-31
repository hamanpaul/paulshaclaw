"""launcher.cli（`paulshaclaw` console script）與邊界測試（#288 A 節）。"""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import zipfile
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


def test_top_level_no_cockpit_flag(monkeypatch) -> None:
    """#334: 頂層 paulshaclaw --no-cockpit 與 paulshaclaw up --no-cockpit 一致。"""
    called: dict[str, bool] = {}

    def fake_up(no_cockpit: bool) -> int:
        called["no_cockpit"] = no_cockpit
        return 0

    monkeypatch.setattr(cli, "_cmd_up", fake_up)
    rc = cli.main(["--no-cockpit"])
    assert rc == 0
    assert called.get("no_cockpit") is True


def test_top_level_default_up(monkeypatch) -> None:
    """#334: 頂層 paulshaclaw 預設執行 _cmd_up(no_cockpit=False)。"""
    called: dict[str, bool] = {}

    def fake_up(no_cockpit: bool) -> int:
        called["no_cockpit"] = no_cockpit
        return 0

    monkeypatch.setattr(cli, "_cmd_up", fake_up)
    rc = cli.main([])
    assert rc == 0
    assert called.get("no_cockpit") is False


def test_explicit_up_default(monkeypatch) -> None:
    """#334: 明確子命令 paulshaclaw up 執行 _cmd_up(no_cockpit=False)。"""
    called: dict[str, bool] = {}

    def fake_up(no_cockpit: bool) -> int:
        called["no_cockpit"] = no_cockpit
        return 0

    monkeypatch.setattr(cli, "_cmd_up", fake_up)
    rc = cli.main(["up"])
    assert rc == 0
    assert called.get("no_cockpit") is False


def test_explicit_up_with_no_cockpit(monkeypatch) -> None:
    """#334: 明確子命令 paulshaclaw up --no-cockpit 執行 _cmd_up(no_cockpit=True)。"""
    called: dict[str, bool] = {}

    def fake_up(no_cockpit: bool) -> int:
        called["no_cockpit"] = no_cockpit
        return 0

    monkeypatch.setattr(cli, "_cmd_up", fake_up)
    rc = cli.main(["up", "--no-cockpit"])
    assert rc == 0
    assert called.get("no_cockpit") is True


def test_pyproject_declares_commands_json_package_data() -> None:
    """#334: pyproject.toml 必須宣告 paulshaclaw.core package-data 包含 commands.json。"""
    payload = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pkg_data = payload.get("tool", {}).get("setuptools", {}).get("package-data", {})
    assert "paulshaclaw.core" in pkg_data, "package-data 缺少 paulshaclaw.core"
    patterns = pkg_data["paulshaclaw.core"]
    assert any("json" in pat for pat in patterns), f"paulshaclaw.core package-data 缺少 json 檔宣告：{patterns}"


def test_release_artifacts_script_checks_commands_json() -> None:
    """#334: scripts/release-artifacts.sh 必須檢查 commands.json package data。"""
    script_text = (REPO_ROOT / "scripts" / "release-artifacts.sh").read_text(encoding="utf-8")
    assert "paulshaclaw/core/commands.json" in script_text or "commands.json" in script_text


def test_built_wheel_contains_commands_json_archive(tmp_path: Path) -> None:
    """#334 Task 1.1: build wheel 並斷言 paulshaclaw/core/commands.json 存在於 archive 中。"""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(tmp_path),
            str(REPO_ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"wheel build 失敗:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"預期 1 個 wheel，找到: {wheels}"
    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
        assert "paulshaclaw/core/commands.json" in names, f"commands.json 未包含於 wheel 內容: {names}"
        assert "paulshaclaw/cockpit/cockpit.tcss" in names
