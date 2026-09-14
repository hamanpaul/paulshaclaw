from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from paulshaclaw import cli


def _install_fake_cortex(monkeypatch: pytest.MonkeyPatch, *, return_value: int = 0, calls: list[list[str]] | None = None) -> None:
    package = types.ModuleType("paulsha_cortex")
    package.__path__ = []  # type: ignore[attr-defined]
    module = types.ModuleType("paulsha_cortex.cli")

    def fake_main(argv: list[str]) -> int:
        if calls is not None:
            calls.append(list(argv))
        return return_value

    module.main = fake_main  # type: ignore[attr-defined]
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object() if name == "paulsha_cortex.cli" else None)
    monkeypatch.setitem(sys.modules, "paulsha_cortex", package)
    monkeypatch.setitem(sys.modules, "paulsha_cortex.cli", module)


@pytest.mark.parametrize(
    ("subcommand", "rest", "expected_argv"),
    [
        ("coordinator", ["jobs", "--json"], ["jobs", "--json"]),
        ("deck", ["list"], ["deck", "list"]),
        ("monitor", ["tail", "worker-1"], ["monitor", "tail", "worker-1"]),
    ],
)
def test_cortex_subcommands_forward_argv(
    monkeypatch: pytest.MonkeyPatch,
    subcommand: str,
    rest: list[str],
    expected_argv: list[str],
) -> None:
    calls: list[list[str]] = []
    _install_fake_cortex(monkeypatch, return_value=7, calls=calls)

    rc = cli.main([subcommand, *rest])

    assert rc == 7
    assert calls == [expected_argv]


@pytest.mark.parametrize("subcommand", ["coordinator", "deck", "monitor"])
def test_cortex_missing_prints_tombstone(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], subcommand: str) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None if name == "paulsha_cortex.cli" else object())
    monkeypatch.delitem(sys.modules, "paulsha_cortex", raising=False)
    monkeypatch.delitem(sys.modules, "paulsha_cortex.cli", raising=False)

    rc = cli.main([subcommand, "anything"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "paulsha-cortex" in err
    assert "pipx install git+https://github.com/hamanpaul/paulsha-cortex" in err


def test_memory_tombstone_still_prints_hippo_guidance(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["memory", "dream", "status"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "paulsha-hippo" in err
    assert "hippo" in err


def test_unknown_argv_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["nosuch"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "usage: psc {coordinator|deck|monitor} <args...>" in err
    assert "psc（無參數）= paulshaclaw up" in err


def test_empty_argv_launches_operator_shell(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """#357：`psc` 不帶參數等同 `paulshaclaw`（up），回傳值透傳、不印 usage。"""
    calls: list[list[str]] = []

    def fake_launcher_main(argv: list[str]) -> int:
        calls.append(list(argv))
        return 5

    monkeypatch.setattr("paulshaclaw.launcher.cli.main", fake_launcher_main)

    rc = cli.main([])

    assert rc == 5
    assert calls == [[]]
    assert capsys.readouterr().err == ""


def test_empty_argv_does_not_forward_launcher_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """#357 非目標：launcher 旗標（--no-cockpit／down／status）不併入 psc，仍屬 paulshaclaw。"""
    monkeypatch.setattr("paulshaclaw.launcher.cli.main", lambda argv: 0)

    assert cli.main(["--no-cockpit"]) == 2
    assert cli.main(["down"]) == 2


def test_cli_source_no_longer_routes_to_repo_subtrees() -> None:
    source = (Path(__file__).resolve().parents[1] / "paulshaclaw" / "cli.py").read_text(encoding="utf-8")
    prefix = "paulshaclaw"

    assert f"{prefix}.coordinator" not in source
    assert f"{prefix}.deck" not in source
    assert f"{prefix}.monitor" not in source
