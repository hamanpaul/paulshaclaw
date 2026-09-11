from __future__ import annotations

import contextlib
import json
import unittest
from io import StringIO
from pathlib import Path
from textwrap import dedent

import yaml

from paulshaclaw.deploy.__main__ import main as deploy_main
from paulshaclaw.deploy.agents import _NEVER_READ, detect_agents, parse_footer_argument, write_footer_config
from paulshaclaw.deploy.footer_select import FooterSelectionApp, FooterSelectionOption


def _run_deploy_main(argv: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exit_code = deploy_main(argv)
        except SystemExit as exc:  # pragma: no cover - defensive
            exit_code = exc.code if isinstance(exc.code, int) else 1
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _drop_enabled(value):
    if isinstance(value, dict):
        return {key: _drop_enabled(item) for key, item in value.items() if key != "enabled"}
    if isinstance(value, list):
        return [_drop_enabled(item) for item in value]
    return value


def test_parse_footer_argument_supports_multi_provider_and_bare_copilot() -> None:
    parsed = parse_footer_argument("codex,claude,copilot:haman:arc,agy")
    bare_copilot = parse_footer_argument("copilot")
    none = parse_footer_argument("none")

    assert set(parsed["providers"]) == {"codex", "claude", "copilot", "agy"}
    assert parsed["providers"]["copilot"]["labels"] == ["haman", "arc"]
    assert parsed["providers"]["copilot"]["all_accounts"] is False
    assert bare_copilot["providers"]["copilot"]["all_accounts"] is True
    assert none["disable_all"] is True


def test_detect_agents_never_reads_guarded_paths(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    (home / ".claude").mkdir(parents=True)
    (home / ".config" / "github-copilot").mkdir(parents=True)
    (home / ".gemini").mkdir(parents=True)
    (home / ".gemini" / "oauth_creds.json").write_text("{}", encoding="utf-8")
    (home / ".gemini" / "antigravity-oauth-token").write_text("token", encoding="utf-8")
    (home / ".gemini" / "google_accounts.json").write_text("[]", encoding="utf-8")

    guarded = {(home / relative).resolve() for relative in _NEVER_READ}
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes
    original_open = Path.open

    def fail_read_text(path: Path, *args, **kwargs):
        if path.resolve() in guarded:
            raise AssertionError(f"guarded read_text: {path}")
        return original_read_text(path, *args, **kwargs)

    def fail_read_bytes(path: Path, *args, **kwargs):
        if path.resolve() in guarded:
            raise AssertionError(f"guarded read_bytes: {path}")
        return original_read_bytes(path, *args, **kwargs)

    def fail_open(path: Path, *args, **kwargs):
        if path.resolve() in guarded:
            raise AssertionError(f"guarded open: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    monkeypatch.setattr(Path, "open", fail_open)
    monkeypatch.setattr("paulshaclaw.deploy.agents.shutil.which", lambda name: f"/usr/bin/{name}")

    detected = detect_agents(home_dir=home)

    assert detected["codex"]["detected"] is True
    assert detected["claude"]["detected"] is True
    assert detected["copilot"]["detected"] is True
    assert detected["agy"]["detected"] is True
    assert detected["claude"]["sidecar_exists"] is False


def test_write_footer_config_creates_backup_and_only_mutates_enabled(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_path = home / ".config" / "paulshaclaw" / "paulshaclaw.yaml"
    config_path.parent.mkdir(parents=True)
    original_text = dedent(
        """
        workspaces:
          - path: ~/repo
            name: repo
        cost:
          providers:
            codex:
              enabled: false
              local_fallback: true
            claude:
              max_age_seconds: 90
            copilot:
              accounts:
                - id: hamanpaul
                  label: haman
                  monthly_allowance: 1500
                - id: org-a
                  label: arc
                  kind: company
                  monthly_allowance: 300
                  org: example-org
            agy:
              source: unknown
              accounts:
                - id: primary
                  label: main
                  enabled: false
        """
    ).strip() + "\n"
    config_path.write_text(original_text, encoding="utf-8")
    before = yaml.safe_load(original_text)

    result = write_footer_config(
        parse_footer_argument("codex,claude,copilot:haman,agy"),
        home_dir=home,
    )

    after = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    backup_path = Path(result["backup_path"])
    copilot_accounts = {
        account["label"]: account["enabled"]
        for account in after["cost"]["providers"]["copilot"]["accounts"]
    }

    assert result["status"] == "written"
    assert backup_path.read_text(encoding="utf-8") == original_text
    assert _drop_enabled(after) == _drop_enabled(before)
    assert after["cost"]["providers"]["codex"]["enabled"] is True
    assert after["cost"]["providers"]["claude"]["enabled"] is True
    assert copilot_accounts == {"haman": True, "arc": False}
    assert after["cost"]["providers"]["agy"]["enabled"] is True
    assert after["cost"]["providers"]["agy"]["accounts"][0]["enabled"] is True


def test_write_footer_config_uses_sample_fallback_when_config_missing(tmp_path: Path) -> None:
    home = tmp_path / "home"

    result = write_footer_config(
        parse_footer_argument("copilot:haman:arc,agy"),
        home_dir=home,
    )

    config_path = home / ".config" / "paulshaclaw" / "paulshaclaw.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    copilot_accounts = {
        account["label"]: account["enabled"]
        for account in payload["cost"]["providers"]["copilot"]["accounts"]
    }

    assert result["source"] == "sample"
    assert result["backup_path"] is None
    assert payload["cost"]["providers"]["codex"]["enabled"] is False
    assert payload["cost"]["providers"]["claude"]["enabled"] is False
    assert copilot_accounts == {"haman": True, "arc": True}
    assert payload["cost"]["providers"]["agy"]["enabled"] is True


def test_install_apply_bare_copilot_flag_writes_all_sample_accounts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "paulshaclaw.deploy.installer._ensure_linger_enabled",
        lambda: "enabled",
    )
    monkeypatch.setattr(
        "paulshaclaw.deploy.installer._run_daemon_reload",
        lambda: "ran",
    )

    exit_code, stdout, stderr = _run_deploy_main(
        [
            "install",
            "--apply",
            "--instance",
            "demo-agent",
            "--root-dir",
            "/srv/paulshaclaw",
            "--home-dir",
            str(tmp_path / "home"),
            "--footer",
            "copilot",
        ]
    )

    payload = json.loads(stdout)
    config_path = tmp_path / "home" / ".config" / "paulshaclaw" / "paulshaclaw.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    enabled_accounts = {
        account["label"]: account["enabled"]
        for account in config["cost"]["providers"]["copilot"]["accounts"]
    }

    assert exit_code == 0
    assert stderr == ""
    assert payload["footer_selection"]["mode"] == "flag"
    assert payload["footer_selection"]["config_write"]["status"] == "written"
    assert enabled_accounts == {"haman": True, "arc": True}


class FooterSelectionAppTests(unittest.IsolatedAsyncioTestCase):
    async def test_toggle_enter_returns_structured_selection(self) -> None:
        app = FooterSelectionApp(
            options=[
                FooterSelectionOption("codex", "provider:codex"),
                FooterSelectionOption("copilot", "provider:copilot"),
                FooterSelectionOption("  └─ copilot:haman", "account:copilot:haman"),
            ],
            preview_builder=lambda values: ",".join(sorted(values)) or "none",
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("down", "down")
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

        assert app.result is not None
        assert app.result["providers"]["codex"]["enabled"] is True
        assert app.result["providers"]["copilot"]["labels"] == ["haman"]

    async def test_escape_returns_none(self) -> None:
        app = FooterSelectionApp(
            options=[FooterSelectionOption("codex", "provider:codex")],
            preview_builder=lambda values: ",".join(sorted(values)) or "none",
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("escape")
            await pilot.pause()

        assert app.result is None

    async def test_undetected_item_can_still_be_checked(self) -> None:
        app = FooterSelectionApp(
            options=[FooterSelectionOption("claude (not detected)", "provider:claude")],
            preview_builder=lambda values: ",".join(sorted(values)) or "none",
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

        assert app.result is not None
        assert app.result["providers"]["claude"]["enabled"] is True
