from __future__ import annotations

from paulshaclaw import cli


def test_route_memory_moved_guidance(capsys) -> None:
    # #125：memory 子樹已遷 paulsha-hippo——指引改用 hippo，exit 2
    rc = cli.main(["memory", "dream", "status"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "paulsha-hippo" in err
    assert "hippo" in err


def test_route_coordinator(monkeypatch) -> None:
    monkeypatch.setattr("paulshaclaw.coordinator.cli.main", lambda argv: 0)

    assert cli.main(["coordinator", "jobs"]) == 0


def test_unknown_subcommand_exit_2(capsys) -> None:
    assert cli.main(["nosuch"]) == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_no_args_exit_2() -> None:
    assert cli.main([]) == 2
