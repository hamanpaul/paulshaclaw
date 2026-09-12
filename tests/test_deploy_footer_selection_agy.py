"""#343: install/TUI 的 agy 多帳號 `--footer agy:<label>[:<label>]` 與 SelectionList。

檔名前綴 `test_deploy_footer_selection` 命中 `tests/conftest.py` 的
`_DEPLOY_TEST_PREFIXES`，取得 `PSC_HOME_ROOT` 家目錄隔離第二道防線。
"""

from __future__ import annotations

import argparse
import unittest
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from paulshaclaw.cost.config import AgyAccountConfig, AgyProviderConfig, CostConfig
from paulshaclaw.deploy.agents import (
    DetectedAgent,
    apply_footer_selection_payload,
    parse_footer_argument,
    preview_footer_selection,
    resolve_footer_enabled,
    write_footer_config,
)
from paulshaclaw.deploy.footer_select import (
    FooterSelectionApp,
    FooterSelectionOption,
    _selection_raw,
    build_selection_options,
    selection_from_values,
)


# --- 7. deploy/agents.py -----------------------------------------------------


def test_parse_footer_argument_agy_supports_labels_and_bare_all_accounts() -> None:
    parsed = parse_footer_argument("agy:me:work")
    assert parsed["providers"]["agy"] == {
        "enabled": True,
        "labels": ["me", "work"],
        "all_accounts": False,
    }

    bare = parse_footer_argument("agy")
    assert bare["providers"]["agy"] == {"enabled": True, "labels": [], "all_accounts": True}


def test_parse_footer_argument_codex_still_rejects_label() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_footer_argument("codex:x")


def test_apply_footer_selection_declares_new_agy_account_and_preserves_existing_fields() -> None:
    payload = {
        "cost": {
            "providers": {
                "agy": {
                    "enabled": False,
                    "group": "3p",
                    "accounts": [
                        {"id": "me", "label": "Me", "enabled": False, "kind": "personal"},
                    ],
                }
            }
        }
    }
    selection = parse_footer_argument("agy:me:work")

    updated = apply_footer_selection_payload(payload, selection)
    agy = updated["cost"]["providers"]["agy"]
    accounts_by_id = {account["id"]: account for account in agy["accounts"]}

    assert agy["enabled"] is True
    assert agy["group"] == "3p"
    assert accounts_by_id["me"]["label"] == "Me"
    assert accounts_by_id["me"]["kind"] == "personal"
    assert accounts_by_id["me"]["enabled"] is True
    assert accounts_by_id["work"] == {"id": "work", "label": "work", "enabled": True}


def test_apply_footer_selection_none_disables_all_agy_accounts() -> None:
    payload = {
        "cost": {
            "providers": {
                "agy": {
                    "enabled": True,
                    "accounts": [
                        {"id": "me", "enabled": True},
                        {"id": "work", "enabled": True},
                    ],
                }
            }
        }
    }
    updated = apply_footer_selection_payload(payload, parse_footer_argument("none"))
    agy = updated["cost"]["providers"]["agy"]

    assert agy["enabled"] is False
    assert {account["id"]: account["enabled"] for account in agy["accounts"]} == {
        "me": False,
        "work": False,
    }


def test_apply_footer_selection_does_not_create_empty_agy_accounts_key() -> None:
    payload = {"cost": {"providers": {"agy": {"enabled": False}}}}
    updated = apply_footer_selection_payload(payload, parse_footer_argument("codex"))

    assert "accounts" not in updated["cost"]["providers"]["agy"]


def test_resolve_footer_enabled_agy_is_bool_without_accounts_and_dict_with_accounts() -> None:
    no_accounts_payload = {"cost": {"providers": {"agy": {"enabled": True}}}}
    enabled = resolve_footer_enabled(payload=no_accounts_payload)
    assert enabled["agy"] is True

    with_accounts_payload = {
        "cost": {
            "providers": {
                "agy": {
                    "enabled": True,
                    "accounts": [
                        {"id": "me", "enabled": True},
                        {"id": "work", "enabled": False},
                    ],
                }
            }
        }
    }
    enabled_dict = resolve_footer_enabled(payload=with_accounts_payload)
    assert enabled_dict["agy"] == {"me": True, "work": False}


def test_preview_footer_selection_shows_labeled_agy_segment() -> None:
    payload = {
        "cost": {
            "providers": {
                "agy": {"accounts": [{"id": "me", "enabled": False}]},
            }
        }
    }
    preview = preview_footer_selection(parse_footer_argument("agy:me"), payload=payload)
    assert "agy/me ?" in preview


def test_write_footer_config_round_trips_agy_accounts_and_backs_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    config_path = home / ".config" / "paulshaclaw" / "paulshaclaw.yaml"
    config_path.parent.mkdir(parents=True)
    monkeypatch.setattr(
        "paulshaclaw.deploy.agents._utc_now",
        lambda: datetime(2026, 9, 13, 9, 30, tzinfo=timezone.utc),
    )
    original_text = (
        dedent(
            """
            cost:
              providers:
                agy:
                  enabled: false
                  accounts:
                    - id: me
                      label: Me
                      enabled: false
                    - id: work
                      label: Work
                      enabled: false
            """
        ).strip()
        + "\n"
    )
    config_path.write_text(original_text, encoding="utf-8")

    result = write_footer_config(parse_footer_argument("agy:me"), home_dir=home)

    after = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    accounts = {account["id"]: account["enabled"] for account in after["cost"]["providers"]["agy"]["accounts"]}
    backup_path = Path(result["backup_path"])

    assert result["status"] == "written"
    assert backup_path.read_text(encoding="utf-8") == original_text
    assert after["cost"]["providers"]["agy"]["enabled"] is True
    assert accounts == {"me": True, "work": False}


# --- 8. deploy/footer_select.py ----------------------------------------------


def test_build_selection_options_includes_agy_account_rows() -> None:
    options = build_selection_options(
        detected_agents=(DetectedAgent("agy", Path("/usr/bin/agy"), True),),
        config=CostConfig(
            agy=AgyProviderConfig(
                enabled=True,
                accounts=(
                    AgyAccountConfig(account_id="me", label="me", enabled=True),
                    AgyAccountConfig(account_id="work", label="work", enabled=False),
                ),
            ),
        ),
    )
    options_by_value = {option.value: option for option in options}

    assert options_by_value["account:agy:me"].selected is True
    assert options_by_value["account:agy:me"].label == "  └─ agy:me"
    assert options_by_value["account:agy:work"].selected is False


def test_build_selection_options_agy_accounts_unchecked_when_undetected() -> None:
    options = build_selection_options(
        detected_agents=(DetectedAgent("agy", None, False),),
        config=CostConfig(
            agy=AgyProviderConfig(
                enabled=True,
                accounts=(AgyAccountConfig(account_id="me", label="me", enabled=True),),
            ),
        ),
    )
    options_by_value = {option.value: option for option in options}

    assert options_by_value["provider:agy"].label == "agy (未偵測)"
    assert options_by_value["provider:agy"].selected is False
    assert options_by_value["account:agy:me"].selected is False
    # 帳號列未偵測時預設不勾，但不像父列那樣加 "(未偵測)" 後綴。
    assert options_by_value["account:agy:me"].label == "  └─ agy:me"


def test_selection_from_values_agy_three_combinations() -> None:
    bare = selection_from_values({"provider:agy"})
    assert bare["providers"]["agy"] == {"enabled": True, "all_accounts": True}

    labeled = selection_from_values({"account:agy:me", "account:agy:work"})
    assert labeled["providers"]["agy"] == {"enabled": True, "labels": ["me", "work"]}

    none_selected = selection_from_values(set())
    assert none_selected["disable_all"] is True
    assert none_selected["providers"] == {}


def test_selection_raw_renders_agy_labels_like_copilot() -> None:
    assert (
        _selection_raw({"agy": {"enabled": True, "labels": ["me", "work"], "all_accounts": False}})
        == "agy:me:work"
    )
    assert _selection_raw({"agy": {"enabled": True, "labels": [], "all_accounts": True}}) == "agy"


class AgyFooterSelectionAppTests(unittest.IsolatedAsyncioTestCase):
    async def test_toggle_agy_account_row_returns_labels(self) -> None:
        app = FooterSelectionApp(
            options=[
                FooterSelectionOption("agy", "provider:agy"),
                FooterSelectionOption("  └─ agy:me", "account:agy:me"),
            ],
            preview_builder=lambda values: ",".join(sorted(values)) or "none",
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

        assert app.result is not None
        assert app.result["providers"]["agy"]["labels"] == ["me"]
