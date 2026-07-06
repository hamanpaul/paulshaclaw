"""tests/test_config_paths.py — paulshaclaw.config.paths facade 單元測試（#91）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from paulshaclaw.config import paths


# ---------------------------------------------------------------------------
# env 覆寫生效
# ---------------------------------------------------------------------------


def test_memory_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(tmp_path / "m"))
    assert paths.memory_root() == tmp_path / "m"


def test_agents_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(tmp_path / "agents"))
    assert paths.agents_root() == tmp_path / "agents"


def test_config_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path / "cfg"))
    assert paths.config_root() == tmp_path / "cfg"


def test_notes_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_NOTES_ROOT", str(tmp_path / "notes"))
    assert paths.notes_root() == tmp_path / "notes"


def test_copilot_state_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_COPILOT_STATE_ROOT", str(tmp_path / "copilot"))
    assert paths.copilot_state_root() == tmp_path / "copilot"


def test_repo_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_REPO_ROOT", str(tmp_path / "repo"))
    assert paths.repo_root() == tmp_path / "repo"


def test_worktree_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_WORKTREE_ROOT", str(tmp_path / "wt"))
    assert paths.worktree_root() == tmp_path / "wt"


def test_extra_corpus_root_env_set(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_EXTRA_CORPUS_ROOT", str(tmp_path / "corpus"))
    assert paths.extra_corpus_root() == tmp_path / "corpus"


# ---------------------------------------------------------------------------
# 未設 env 走契約預設
# ---------------------------------------------------------------------------


def test_default_contract(monkeypatch, tmp_path):
    for k in (
        "PSC_MEMORY_ROOT",
        "PSC_AGENTS_ROOT",
        "PSC_CONFIG_ROOT",
        "PSC_NOTES_ROOT",
        "PSC_COPILOT_STATE_ROOT",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert paths.home() == tmp_path
    assert paths.agents_root() == tmp_path / ".agents"
    assert paths.memory_root() == tmp_path / ".agents" / "memory"
    assert paths.config_root() == tmp_path / ".config" / "paulshaclaw"
    assert paths.notes_root() == tmp_path / "notes"
    assert paths.copilot_state_root() == tmp_path / ".copilot" / "session-state"


def test_extra_corpus_root_unset_returns_none(monkeypatch):
    monkeypatch.delenv("PSC_EXTRA_CORPUS_ROOT", raising=False)
    assert paths.extra_corpus_root() is None


# ---------------------------------------------------------------------------
# PSC_MEMORY_ROOT 覆寫時 agents_root 回傳契約預設（兩者獨立）
# ---------------------------------------------------------------------------


def test_memory_root_independent_of_agents_root(monkeypatch, tmp_path):
    monkeypatch.delenv("PSC_AGENTS_ROOT", raising=False)
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(tmp_path / "custom_mem"))
    monkeypatch.setenv("HOME", str(tmp_path))

    assert paths.memory_root() == tmp_path / "custom_mem"
    assert paths.agents_root() == tmp_path / ".agents"


# ---------------------------------------------------------------------------
# repo_root 預設由 __file__ 反推（不依賴 HOME）
# ---------------------------------------------------------------------------


def test_repo_root_default_is_two_levels_above_paths_py(monkeypatch):
    monkeypatch.delenv("PSC_REPO_ROOT", raising=False)
    expected = Path(__file__).resolve().parents[1]
    # repo_root 應為 repo 根（paulshaclaw/config/paths.py 的上上層）
    assert paths.repo_root() == expected


# ---------------------------------------------------------------------------
# worktree_root 跟隨 repo_root
# ---------------------------------------------------------------------------


def test_worktree_root_follows_repo_root(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_REPO_ROOT", str(tmp_path / "myrepo"))
    monkeypatch.delenv("PSC_WORKTREE_ROOT", raising=False)
    assert paths.worktree_root() == tmp_path / "myrepo-worktrees"


# ---------------------------------------------------------------------------
# expanduser 支援（~ 前綴）
# ---------------------------------------------------------------------------


def test_expanduser_in_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PSC_MEMORY_ROOT", "~/custom_mem")
    assert paths.memory_root() == tmp_path / "custom_mem"
