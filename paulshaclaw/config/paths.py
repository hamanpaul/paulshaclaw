"""路徑 facade——唯一 Path.home() 推導點（#91；path-split 契約不變）。

優先序：對應 PSC_* 環境變數 > XDG/path-split 契約預設。
本模組 stdlib-only，禁 import 業務包（防環）。
"""
from __future__ import annotations

import os
from pathlib import Path


def _root(env: str, default: Path) -> Path:
    value = os.environ.get(env, "").strip()
    return Path(value).expanduser() if value else default


def home() -> Path:
    """回傳使用者家目錄（唯一合法的 Path.home() 呼叫點）。"""
    return Path.home()


def agents_root() -> Path:
    """~/.agents（可由 PSC_AGENTS_ROOT 覆寫）。"""
    return _root("PSC_AGENTS_ROOT", home() / ".agents")


def memory_root() -> Path:
    """~/.agents/memory（可由 PSC_MEMORY_ROOT 覆寫）。"""
    return _root("PSC_MEMORY_ROOT", agents_root() / "memory")


def config_root() -> Path:
    """~/.config/paulshaclaw（可由 PSC_CONFIG_ROOT 覆寫）。"""
    return _root("PSC_CONFIG_ROOT", home() / ".config" / "paulshaclaw")


def notes_root() -> Path:
    """~/notes（可由 PSC_NOTES_ROOT 覆寫）。"""
    return _root("PSC_NOTES_ROOT", home() / "notes")


def copilot_state_root() -> Path:
    """~/.copilot/session-state（可由 PSC_COPILOT_STATE_ROOT 覆寫）。"""
    return _root("PSC_COPILOT_STATE_ROOT", home() / ".copilot" / "session-state")


def repo_root() -> Path:
    """Repo 根目錄（可由 PSC_REPO_ROOT 覆寫；預設從 __file__ 反推兩層）。"""
    return _root("PSC_REPO_ROOT", Path(__file__).resolve().parents[2])


def worktree_root() -> Path:
    """Worktree 根目錄（可由 PSC_WORKTREE_ROOT 覆寫；預設 repo_root 同層 -worktrees 目錄）。"""
    r = repo_root()
    return _root("PSC_WORKTREE_ROOT", r.parent / f"{r.name}-worktrees")


def extra_corpus_root() -> Path | None:
    """PSC_EXTRA_CORPUS_ROOT 指定的額外 corpus 目錄；未設則為 None。

    收編 P0-1 Stage A 過渡 env（別名保留一版）。
    """
    value = os.environ.get("PSC_EXTRA_CORPUS_ROOT", "").strip()
    return Path(value).expanduser() if value else None
