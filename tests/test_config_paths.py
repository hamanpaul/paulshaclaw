from pathlib import Path

from paulshaclaw.config import paths


def test_env_override(monkeypatch, tmp_path):
    memory_root = tmp_path / "memory"
    monkeypatch.setenv("PSC_MEMORY_ROOT", str(memory_root))

    assert paths.memory_root() == memory_root


def test_default_contract(monkeypatch, tmp_path):
    for key in (
        "PSC_AGENTS_ROOT",
        "PSC_MEMORY_ROOT",
        "PSC_CONFIG_ROOT",
        "PSC_NOTES_ROOT",
        "PSC_COPILOT_ROOT",
        "PSC_MAX_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert paths.agents_root() == tmp_path / ".agents"
    assert paths.memory_root() == tmp_path / ".agents" / "memory"
    assert paths.config_root() == tmp_path / ".config" / "paulshaclaw"
    assert paths.notes_root() == tmp_path / "notes"
    assert paths.state_path("telegram-chat-bindings.json") == tmp_path / ".agents" / "state" / "telegram-chat-bindings.json"
    assert paths.copilot_history_root() == tmp_path / ".copilot" / "history-session-state"
    assert paths.max_root() == tmp_path / ".max"


def test_legacy_psc_config_root_still_maps_to_contract_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path))

    assert paths.config_root() == tmp_path / ".config" / "paulshaclaw"
    assert paths.copilot_root() == tmp_path / ".copilot"


def test_worktree_root_prefers_existing_repo_pool(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    worktree_pool = repo_root / ".worktrees"
    worktree_checkout = worktree_pool / "feature-env-facade"
    worktree_checkout.mkdir(parents=True)
    monkeypatch.delenv("PSC_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("PSC_REPO_ROOT", str(worktree_checkout))

    assert paths.worktree_root() == worktree_pool


def test_runtime_consumers_resolve_overrides_after_import(monkeypatch, tmp_path):
    from paulshaclaw.bot import reply
    from paulshaclaw.coordinator import registry, seams

    agents_root = tmp_path / "agents"
    repo_root = tmp_path / "repo"
    worktree_root = tmp_path / "worktrees"
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("PSC_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("PSC_WORKTREE_ROOT", str(worktree_root))

    assert registry.JobRegistry()._state_path == agents_root / "coordinator" / "jobs.json"
    creator = seams.ScriptWorktreeCreator()
    assert creator._repo == repo_root
    assert creator._wt_root == worktree_root
    assert reply.default_config_path() == tmp_path / ".config" / "paulshaclaw" / "paulshaclaw.state.json"
    assert reply.default_secret_env_path() == tmp_path / ".config" / "paulshaclaw" / "paulshaclaw.telegram.secret.env"
    assert reply.default_bindings_path() == agents_root / "state" / "telegram-chat-bindings.json"


def test_cost_and_monitor_helpers_follow_facade(monkeypatch, tmp_path):
    from paulshaclaw.cost import config as cost_config
    from paulshaclaw.monitor import config as monitor_config

    agents_root = tmp_path / "agents"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(agents_root))
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path))

    assert cost_config.default_config_path() == tmp_path / ".config" / "paulshaclaw" / "paulshaclaw.yaml"
    assert cost_config.default_claude_statusline_sidecar() == agents_root / "state" / "cost" / "claude_rate_limits.json"
    assert cost_config.default_codex_auth_path() == tmp_path / ".codex" / "auth.json"
    assert cost_config.default_cost_cache_dir() == agents_root / "state" / "cost"
    assert cost_config.default_cost_log_path() == agents_root / "log" / "cost.log"
    assert monitor_config.default_config_path() == tmp_path / ".config" / "paulshaclaw" / "paulshaclaw.yaml"
    assert monitor_config.default_socket_path() == agents_root / "run" / "project-monitor.sock"


def test_extra_corpus_root(monkeypatch, tmp_path):
    extra = tmp_path / "extra-corpus"
    monkeypatch.setenv("PSC_EXTRA_CORPUS_ROOT", str(extra))

    assert paths.extra_corpus_root() == extra
