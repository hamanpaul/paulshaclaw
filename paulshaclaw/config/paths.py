from __future__ import annotations

import os
from pathlib import Path

PathPart = str | os.PathLike[str]


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def _resolve_root(name: str, default: Path) -> Path:
    return _env_path(name) or default


def _join(root: Path, *parts: PathPart) -> Path:
    return root.joinpath(*parts)


def _is_contract_config_root(path: Path) -> bool:
    return path.name == "paulshaclaw" and path.parent.name == ".config"


def _legacy_config_base_root() -> Path | None:
    override = _env_path("PSC_CONFIG_ROOT")
    if override is None:
        return None
    if _is_contract_config_root(override):
        return override.parents[1]
    return override


def home_root() -> Path:
    return Path.home()


def home_path(*parts: PathPart) -> Path:
    return _join(home_root(), *parts)


def repo_root() -> Path:
    return _resolve_root("PSC_REPO_ROOT", Path(__file__).resolve().parents[2])


def _canonical_repo_root(repo: Path) -> Path:
    if repo.parent.name == ".worktrees":
        return repo.parent.parent
    return repo


def worktree_root() -> Path:
    override = _env_path("PSC_WORKTREE_ROOT")
    if override is not None:
        return override
    repo = _canonical_repo_root(repo_root())
    if (repo / ".worktrees").exists():
        return repo / ".worktrees"
    if (repo / "worktrees").exists():
        return repo / "worktrees"
    return repo.parent / f"{repo.name}-worktrees"


def agents_root() -> Path:
    return _resolve_root("PSC_AGENTS_ROOT", home_root() / ".agents")


def agents_path(*parts: PathPart) -> Path:
    return _join(agents_root(), *parts)


def coordinator_root() -> Path:
    return _resolve_root("PSC_COORDINATOR_ROOT", agents_path("coordinator"))


def memory_root() -> Path:
    return _resolve_root("PSC_MEMORY_ROOT", agents_path("memory"))


def memory_path(*parts: PathPart) -> Path:
    return _join(memory_root(), *parts)


def config_root() -> Path:
    override = _env_path("PSC_CONFIG_ROOT")
    if override is None:
        return home_root() / ".config" / "paulshaclaw"
    if _is_contract_config_root(override):
        return override
    return override / ".config" / "paulshaclaw"


def config_path(*parts: PathPart) -> Path:
    return _join(config_root(), *parts)


def notes_root() -> Path:
    return _resolve_root("PSC_NOTES_ROOT", home_root() / "notes")


def run_root() -> Path:
    return _resolve_root("PSC_RUN_ROOT", agents_path("run"))


def state_root() -> Path:
    return _resolve_root("PSC_STATE_ROOT", agents_path("state"))


def state_path(*parts: PathPart) -> Path:
    return _join(state_root(), *parts)


def log_root() -> Path:
    return _resolve_root("PSC_LOG_ROOT", agents_path("log"))


def control_root() -> Path:
    return _resolve_root("PSC_CONTROL_ROOT", agents_path("control"))


def specs_root() -> Path:
    return _resolve_root("PSC_SPECS_ROOT", agents_path("specs"))


def copilot_root() -> Path:
    return _resolve_root(
        "PSC_COPILOT_ROOT",
        (_legacy_config_base_root() or home_root()) / ".copilot",
    )


def copilot_history_root() -> Path:
    return _join(copilot_root(), "history-session-state")


def copilot_session_state_root() -> Path:
    return _join(copilot_root(), "session-state")


def max_root() -> Path:
    return _resolve_root("PSC_MAX_ROOT", home_root() / ".max")


def claude_root() -> Path:
    return _resolve_root("PSC_CLAUDE_ROOT", home_path(".claude"))


def codex_root() -> Path:
    return _resolve_root("PSC_CODEX_ROOT", home_path(".codex"))


def extra_corpus_root() -> Path | None:
    return _env_path("PSC_EXTRA_CORPUS_ROOT")


def projects_config_path(memory_root_value: str | Path | None = None) -> Path:
    base_root = _legacy_config_base_root()
    if base_root is not None:
        return base_root / ".agents" / "config" / "projects.yaml"
    if memory_root_value is not None:
        return Path(memory_root_value).expanduser().parent / "config" / "projects.yaml"
    return agents_path("config", "projects.yaml")
