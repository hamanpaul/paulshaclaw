### Changed
- env-path facade（#91）：新增 `paulshaclaw/config/paths.py`——唯一 `Path.home()` 呼叫點，全 root `PSC_*` env 覆寫鏈（repo/agents/memory/config/control/copilot/claude/codex…）；43 檔散落路徑遷移經 facade（facade 外 grep-zero）；收編 `PSC_EXTRA_CORPUS_ROOT`；`agent_exec.upstream_url` 讀取集中 config 層
