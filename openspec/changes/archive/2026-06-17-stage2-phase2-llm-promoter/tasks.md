## 1. 輸出窗 env override（TDD）

- [x] 1.1 RED：`test_agent_exec` —— `AgentExecClient(env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS":"8192"})` 時 stub 印出的該值等於傳入；`env=None` 時子程序繼承父 env 不變
- [x] 1.2 GREEN：`agent_exec.py` `AgentExecClient.__init__` 加 `env: dict|None`，`subprocess.run(..., env=None if self._env is None else {**os.environ, **self._env})`
- [x] 1.3 RED：`test_atomizer_config` —— 解析 `agent_exec.max_output_tokens`（預設 8192、非正整數 raise、值併入 config_hash）
- [x] 1.4 GREEN：`config.py` `AtomizerConfig` 加 `agent_exec_max_output_tokens: int = 8192`、loader 用 `_parse_positive_int` 解析、`atomizer.yaml` 補欄位

## 2. CLI 組裝（TDD）

- [x] 2.1 RED：`test_atomizer_cli` —— `_build_promoter(args, config, root)`（llm）建的 `AgentExecClient` 帶 env `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 等於 `config.agent_exec_max_output_tokens`
- [x] 2.2 GREEN：`cli.py:_build_promoter` 把 `{"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(config.agent_exec_max_output_tokens)}` 傳給 `AgentExecClient(command, timeout=..., env=...)`

## 3. LLM 原子 frontmatter 補欄（TDD，雙層 MOC 前置）

- [x] 3.1 RED：`test_slice_frontmatter` —— `build_from_proposal` 把 `session_title`（取自 `session_meta`）與 `atom_title`（取自 `proposal.title`）寫進 frontmatter；`render` 以 free-text 引號輸出兩者
- [x] 3.2 GREEN：`pipeline._promote_pass` 組 `session_meta` 時帶入 `fragment.session_title`；`build_from_proposal` 寫 `session_title`+`atom_title`；`_SCALAR_ORDER` 加 `atom_title` 並比照 `session_title` 引號處理

## 4. 雙層 MOC（TDD）

- [x] 4.1 RED：`test_moc_builder` —— 同一 `source_session` 多原子的 project，渲染成「母 `session_title` + 巢狀子列」階層（非扁平重複標題）；子列標籤取 `atom_title or session_title or basename`
- [x] 4.2 RED：無原子 / 缺 `session_title` 退化為單列、不報錯；identity（有 session_title 無 atom_title）/llm 混血 rows 渲染成功且決定性
- [x] 4.3 GREEN：`_active_slices` 多讀 `atom_title`；`build_mocs` 依 `source_session` 分組、母列 `session_title`、子列縮排掛 `alias_link`，相容混血

## 5. 整線驗證（既有 LLMPromoter 不改，確認 Phase 2a 端到端）

- [x] 5.1 整合測試：`pipeline.run(promoter=LLMPromoter(FakeAgentClient(...)))` → 多原子寫 `knowledge/`、frontmatter 帶 `session_title`+`atom_title`+`distilled_from`、processing 記 `promoter=llm`+`model`+`skill_hash`；雙層 MOC 反映
- [x] 5.2 fail-closed 回歸：fake 回壞 JSON → session 留 split、零 slice（既有語意不破）
- [x] 5.3 `atomize --promoter llm --dry-run` 指 stub fixture → CI 確定性；`unittest discover -s paulshaclaw/memory/tests` 與 `tests/` 全綠

## 6. 啟用

- [x] 6.1 翻 `scripts/start.sh:195` dream loop `--promoter identity` → `--promoter llm`（重啟 start.sh 後啟動 forward-only canary）
- [x] 6.2 R-18：`code_paths` 有變動時同步 `README.md` / `docs/**`（或上 `policy-exempt:docs-sync`）

> Phase 2b（全量回填重蒸餾 + janitor decay）為後續獨立 change，canary 人工判過關才動，不在本 PR。
