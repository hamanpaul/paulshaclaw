import importlib
import subprocess
import sys
from pathlib import Path

import pytest


def _import_or_fail(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"required module is not installed: {module_name}: {exc}")


def _clear_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "PSC_AGENTS_ROOT",
        "PSC_CONTROL_ROOT",
        "PSC_COORDINATOR_ROOT",
        "PSC_SPECS_ROOT",
        "PSC_WORKTREE_ROOT",
        "PSC_REPO_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_cortex_phases_match_hippo_schema():
    hippo_schema = _import_or_fail("paulsha_hippo.lib.lifecycle.schema")
    cortex_contract = _import_or_fail("paulsha_cortex.persona.contract")

    assert cortex_contract.PHASES == hippo_schema.PHASES


@pytest.mark.parametrize(
    ("func_name", "env_name"),
    [
        ("control_root", "PSC_CONTROL_ROOT"),
        ("coordinator_root", "PSC_COORDINATOR_ROOT"),
        ("specs_root", "PSC_SPECS_ROOT"),
        ("worktree_root", "PSC_WORKTREE_ROOT"),
        ("repo_root", "PSC_REPO_ROOT"),
    ],
)
def test_repo_and_cortex_path_roots_align_under_same_overrides(monkeypatch, tmp_path, func_name, env_name):
    repo_paths = _import_or_fail("paulshaclaw.config.paths")
    cortex_paths = _import_or_fail("paulsha_cortex.config.paths")
    _clear_path_env(monkeypatch)

    expected = tmp_path / env_name.lower()
    monkeypatch.setenv(env_name, str(expected))

    assert getattr(repo_paths, func_name)() == expected
    assert getattr(cortex_paths, func_name)() == expected


def test_control_root_defaults_align_between_repo_and_cortex(monkeypatch, tmp_path):
    repo_paths = _import_or_fail("paulshaclaw.config.paths")
    cortex_paths = _import_or_fail("paulsha_cortex.config.paths")
    _clear_path_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))

    expected = tmp_path / ".agents" / "control"
    assert repo_paths.control_root() == expected
    assert cortex_paths.control_root() == expected


def test_deck_persona_bindings_exist_in_cortex_persona_catalog():
    cortex_contract = _import_or_fail("paulsha_cortex.persona.contract")
    deck_schema = _import_or_fail("paulsha_cortex.deck.schema")

    catalog = cortex_contract.load_catalog()
    roles = set(catalog)
    cards = deck_schema.load_cards(deck_schema.DEFAULT_CARDS_PATH)
    referenced_skills = {
        card_id
        for contract in catalog.values()
        for card_id in getattr(contract, "skills", ())
    }
    missing_cards = sorted(card_id for card_id in referenced_skills if card_id not in cards)
    referenced_cards = referenced_skills - set(missing_cards)

    assert missing_cards == []

    missing = {
        card_id: card.persona_binding
        for card_id, card in cards.items()
        if card_id in referenced_cards and card.persona_binding is not None and card.persona_binding not in roles
    }

    assert missing == {}


def test_cortex_package_does_not_depend_on_hippo():
    pip = Path(sys.executable).with_name("pip")
    result = subprocess.run(
        [str(pip), "show", "paulsha-cortex"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout or "pip show paulsha-cortex failed"

    requires_line = next((line for line in result.stdout.splitlines() if line.startswith("Requires:")), "Requires:")
    requires = {
        item.strip().lower()
        for item in requires_line.removeprefix("Requires:").split(",")
        if item.strip()
    }

    assert "paulsha-hippo" not in requires
