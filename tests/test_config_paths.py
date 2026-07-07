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


def test_worktree_root_mirrors_helper_script_sibling_contract(monkeypatch, tmp_path):
    """派工池預設=sibling <repo>-worktrees（鏡射 using-git-worktrees.sh），
    即使 repo 內存在 .worktrees/ 也不得自動偏好（#218 F2）。"""
    repo_root = tmp_path / "repo"
    (repo_root / ".worktrees").mkdir(parents=True)  # 其他工具的池，須被忽略
    monkeypatch.delenv("PSC_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("PSC_REPO_ROOT", str(repo_root))

    assert paths.worktree_root() == tmp_path / "repo-worktrees"


def test_worktree_root_canonicalizes_nested_worktree_checkout(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    worktree_checkout = repo_root / ".worktrees" / "feature-x"
    worktree_checkout.mkdir(parents=True)
    monkeypatch.delenv("PSC_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("PSC_REPO_ROOT", str(worktree_checkout))

    assert paths.worktree_root() == tmp_path / "repo-worktrees"


def test_worktree_root_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_WORKTREE_ROOT", str(tmp_path / "pool"))

    assert paths.worktree_root() == tmp_path / "pool"


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


def test_projects_config_precedence_preserves_legacy_contract(monkeypatch, tmp_path):
    """#218 F3：語意固化——PSC_CONFIG_ROOT（legacy）優先於 memory_root/agents root，
    與 main 時代 default_projects_path 行為一致（facade 為零行為變更遷移；
    優先序重設計屬 paulsha-hippo HIPPO_* 鏈，另案）。"""
    monkeypatch.setenv("PSC_CONFIG_ROOT", str(tmp_path / "legacy"))
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(tmp_path / "isolated-agents"))

    assert paths.projects_config_path() == tmp_path / "legacy" / ".agents" / "config" / "projects.yaml"
    assert (
        paths.projects_config_path(tmp_path / "mem" / "root")
        == tmp_path / "legacy" / ".agents" / "config" / "projects.yaml"
    )

    monkeypatch.delenv("PSC_CONFIG_ROOT", raising=False)
    assert paths.projects_config_path(tmp_path / "mem" / "root") == tmp_path / "mem" / "config" / "projects.yaml"
    assert paths.projects_config_path() == tmp_path / "isolated-agents" / "config" / "projects.yaml"


def test_facade_is_sole_path_home_callsite():
    """grep-zero 強制：facade 本體以外 source 禁 Path.home()。
    白名單：memory/hooks/**（複製部署的自足腳本，#218 F1——不得 import 本 package）。"""
    import ast

    pkg_root = Path(paths.__file__).resolve().parents[2]
    facade = Path(paths.__file__).resolve()
    offenders = []
    for py in sorted((pkg_root / "paulshaclaw").rglob("*.py")):
        rel = py.relative_to(pkg_root)
        if py == facade or "tests" in rel.parts or rel.parts[:3] == ("paulshaclaw", "memory", "hooks"):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "home"
                and isinstance(node.value, ast.Name)
                and node.value.id == "Path"
            ):
                offenders.append(str(rel))
                break
    assert offenders == []


def test_session_end_capture_path_stays_stdlib_only():
    """#218 F1 回歸：session-end 截取 hooks 為複製部署腳本，module-level
    禁止 import paulshaclaw.*——package import 失敗不得讓 queue write 前就死掉。
    （session_start/wakeup 類經 _bootstrap 的函式內 fail-open import 屬 main 既有慣例，不在此限。）"""
    import ast

    pkg_root = Path(paths.__file__).resolve().parents[2]
    hooks_dir = pkg_root / "paulshaclaw" / "memory" / "hooks"
    capture_hooks = ["claude_session_end.py", "codex_session_end.py", "copilot_session_end.py"]
    offenders = []
    for name in capture_hooks:
        tree = ast.parse((hooks_dir / name).read_text(encoding="utf-8"))
        for node in tree.body:  # module-level only
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            if any(n == "paulshaclaw" or n.startswith("paulshaclaw.") for n in names):
                offenders.append(name)
                break
    assert offenders == []


def test_copied_session_end_hook_runs_without_package(tmp_path):
    """#218 F1 部署情境回歸：把 hook 複製到套件外目錄、無 repo cwd/PYTHONPATH，
    餵 stdin JSON 後必須 exit 0 且 queue 檔寫入（fail-open 截取不丟）。"""
    import json as _json
    import shutil
    import subprocess
    import sys as _sys

    pkg_root = Path(paths.__file__).resolve().parents[2]
    src = pkg_root / "paulshaclaw" / "memory" / "hooks" / "claude_session_end.py"
    deploy_dir = tmp_path / "deployed-hooks"
    deploy_dir.mkdir()
    hook = deploy_dir / "claude_session_end.py"
    shutil.copy(src, hook)
    memory_root = tmp_path / "memory"

    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PSC_MEMORY_ROOT": str(memory_root),
        "PSC_IMPORTER_DISABLED": "1",
    }
    payload = {"session_id": "deploy-selfcontained-test", "transcript_path": str(tmp_path / "t.jsonl")}
    completed = subprocess.run(
        [_sys.executable, str(hook)],
        input=_json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(tmp_path),
        env=env,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    queue = list((memory_root / "runtime" / "queue").glob("claude-code__*.json"))
    assert queue, "queue 檔未寫入——複製部署截取失效"
