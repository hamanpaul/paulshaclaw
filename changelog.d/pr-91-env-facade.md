# refactor: env facade — 消滅散落 Path.home()（Closes #91）

## 變更摘要

新增 `paulshaclaw/config/paths.py`，作為全套件唯一的路徑推導點（facade）。

### 新增

- `paulshaclaw/config/__init__.py`：將 `config/` 升級為 package。
- `paulshaclaw/config/paths.py`：stdlib-only env facade，提供：
  - `home()` — 唯一合法的 `Path.home()` 呼叫點。
  - `agents_root()` — `PSC_AGENTS_ROOT` 或 `~/.agents`。
  - `memory_root()` — `PSC_MEMORY_ROOT` 或 `~/.agents/memory`。
  - `config_root()` — `PSC_CONFIG_ROOT` 或 `~/.config/paulshaclaw`。
  - `notes_root()` — `PSC_NOTES_ROOT` 或 `~/notes`。
  - `copilot_state_root()` — `PSC_COPILOT_STATE_ROOT` 或 `~/.copilot/session-state`。
  - `repo_root()` — `PSC_REPO_ROOT` 或 `__file__` 反推兩層。
  - `worktree_root()` — `PSC_WORKTREE_ROOT` 或 repo 同層 `-worktrees`。
  - `extra_corpus_root()` — `PSC_EXTRA_CORPUS_ROOT` 或 `None`（收編 P0-1 Stage A 過渡 env）。
- `tests/test_config_paths.py`：14 項單元測試，涵蓋 env 覆寫、契約預設、expanduser、獨立性。

### 重構（零行為變更）

26 處 `Path.home()` 直接呼叫點與 2 處硬編碼 `/home/...` 路徑已遷移至 facade：

| 受影響模組 | 遷移內容 |
|---|---|
| `memory/hooks/_wakeup_common.py` | `memory_root()` 改呼叫 facade |
| `memory/hooks/claude_session_end.py` | `_memory_root()` 改呼叫 facade |
| `memory/hooks/codex_session_end.py` | `_memory_root()` 改呼叫 facade |
| `memory/hooks/copilot_session_end.py` | `_memory_root()` 與 `_config_root()` 改呼叫 facade |
| `memory/importer/adapters/copilot.py` | `Path.home()` fallback → `paths.home()` |
| `memory/importer/config.py` | `default_projects_path()` → `paths.agents_root()` |
| `memory/importer/backfill.py` | 硬編碼 `/home/paul_chen/...` 預設 → `paths.memory_root()` |
| `memory/instruction_corpus.py` | `default_roots()` 改呼叫 facade；收編 PSC_EXTRA_CORPUS_ROOT |
| `memory/atomizer/config.py` | override 預設路徑 → `paths.config_root()` |
| `memory/janitor/config.py` | override 預設路徑 → `paths.config_root()` |
| `memory/policy/loader.py` | override 預設路徑 → `paths.config_root()` |
| `memory/skillopt/cli.py` | `_default_memory_root/reference_root()` → facade |
| `memory/wakeup/cli.py` | `--memory-root` 預設 → `paths.memory_root()` |
| `memory/cli.py` | `--memory-root`/`--reference-root` 預設 → facade |
| `control/constants.py` | `control_root()` fallback → `paths.agents_root()` |
| `coordinator/manager_daemon.py` | `default_specs_dir()` → `paths.agents_root()` |
| `coordinator/registry.py` | `DEFAULT_STATE_PATH` → `paths.agents_root()` |
| `coordinator/seams.py` | 硬編碼 `/home/paul_chen/...` → `paths.repo_root()/worktree_root()` |
| `core/tmate.py` | 兩個 `_default_*_path()` → `paths.agents_root()` |
| `cost/providers.py` | `_read_local_observed_metrics()` → `paths.copilot_state_root()` |
| `bot/reply.py` | 三個 `DEFAULT_*_PATH` → facade |

### 驗收

- `grep -rn "Path\.home()" paulshaclaw --include='*.py' | grep -v '/tests/' | grep -v 'config/paths.py'` → 0 命中。
- `grep -rn "/home/" paulshaclaw scripts --include='*.py' | grep -v '/tests/'` → 0 命中。
- 全套件 `pytest tests/ paulshaclaw/memory/tests/ -q`：1644 passed（4 pre-existing failures 不變）。

### 部署注意（hooks 複製部署）

hooks 目錄（`memory/hooks/`）現在 import `paulshaclaw.config.paths`。若 hooks 是複製部署，重跑 `install.sh --skip-venv` 使安裝目的地同步更新。
