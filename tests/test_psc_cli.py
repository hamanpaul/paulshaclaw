from __future__ import annotations

from paulshaclaw import cli


def test_route_memory(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_main(argv):
        called.setdefault("argv", argv)
        return 0

    monkeypatch.setattr("paulshaclaw.memory.cli.main", fake_main)
    rc = cli.main(["memory", "dream", "status"])

    assert rc == 0
    assert called["argv"] == ["memory", "dream", "status"]


def test_route_coordinator(monkeypatch) -> None:
    monkeypatch.setattr("paulshaclaw.coordinator.cli.main", lambda argv: 0)

    assert cli.main(["coordinator", "jobs"]) == 0


def test_unknown_subcommand_exit_2(capsys) -> None:
    assert cli.main(["nosuch"]) == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_no_args_exit_2() -> None:
    assert cli.main([]) == 2
