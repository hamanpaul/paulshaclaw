## 1. 共用 transcript reader（base.py）

- [ ] 1.1 新增 fixtures：一段 claude `.jsonl`、一個含 `last_assistant_message` 的 codex payload、一個含 `chatMessages` 的 copilot history JSON
- [ ] 1.2 (RED) `tests/test_adapter_content.py`：斷言三格式 reader 各自抽出非空 prompts / touched_files / 標題輸入
- [ ] 1.3 `adapters/base.py` 新增 `read_claude_transcript`（type=user→prompts、tool_use Write/Edit→touched_files、末則 assistant→標題輸入）、`read_codex_rollout`、`read_copilot_history`
- [ ] 1.4 `adapters/base.py`：`extract_assistant_summary` 加認 `last_assistant_message`；`history_items` 加認 `chatMessages`
- [ ] 1.5 (GREEN) 1.2 測試通過

## 2. 三家 adapter 接線

- [ ] 2.1 (RED) 測試：三家 `extract()` 經 `build_session` 後 `user_prompts`/`touched_files` 非空；transcript 缺檔時留空且不報錯
- [ ] 2.2 `adapters/claude.py`：呼叫 `read_claude_transcript` 後 enrich payload 再 `build_session`
- [ ] 2.3 `adapters/codex.py`：用 payload `last_assistant_message`＋（存在時）`read_codex_rollout` 補 prompts
- [ ] 2.4 `adapters/copilot.py`：由 `session_id` 定位 history-state 檔→`read_copilot_history`
- [ ] 2.5 (GREEN) 2.1 測試通過

## 3. Per-session 標題（title.py）

- [ ] 3.1 (RED) `tests/test_title.py`：**mock LLM**——可達時回 gemma4 標題、≤20 字、`title_source=gemma4`；離線/逾時時 fallback＝首條 prompt 截斷 20 字、`title_source=fallback`
- [ ] 3.2 `importer/title.py`：gemma4 client（`scripts/claude-gemma4` 或 :8001）＋20 字截斷＋離線 fallback，永不丟例外
- [ ] 3.3 importer pipeline 接 `title.generate`：寫入 `assistant_summary`（即標題）、frontmatter `title`、`title_source`
- [ ] 3.4 (GREEN) 3.1 測試通過

## 4. 解 atomize 斜線封鎖（#2）

- [ ] 4.1 (RED) 測試：`sanitize_project_component('github.com/hamanpaul/serialwrap')` 為 path-safe；atomize 整合測試斷言斜線 project 不再被 skip 且產出 slice，原 `project` 值留 metadata
- [ ] 4.2 `atomizer/config.py`：新增 `sanitize_project_component()`（`/`→path-safe，保留可逆性供 metadata）
- [ ] 4.3 `atomizer/pipeline.py`：`_split_pass` 安全檢查、`inbox/_slices/<project>`、`_knowledge_path_for` 改用消毒值；rich `project` 寫入 slice frontmatter
- [ ] 4.4 (GREEN) 4.1 測試通過

## 5. projects.yaml 補登（#2 輔）

- [ ] 5.1 將 serialwrap、OCP-0602、arcadyan airoha feed 等活躍專案補進 `~/.agents/config/projects.yaml`（slug / roots / remotes / aliases）
- [ ] 5.2 驗證 `project_resolver` 對這些 root/remote 回乾淨 slug（無斜線）

## 6. 回填（backfill.py）

- [ ] 6.1 (RED) `tests/test_backfill.py`：`--dry-run` 不寫檔；重入冪等；dead transcript pointer 留空跳過
- [ ] 6.2 `importer/backfill.py`：掃 `archive/queue/**/*.json` 三家強制重抽（繞 checksum dedup）＋ `--dry-run`
- [ ] 6.3 (GREEN) 6.1 測試通過

## 7. 整合與驗證

- [ ] 7.1 端到端整合測試：fixture queue → 跑 importer → 斷言 inbox `.md` 有內容＋非空 ≤20 字標題（不依賴實機 gemma4）
- [ ] 7.2 全 `pytest` 綠；`test_atomizer_llm_live` 維持 live-only/skip；CI `tests.yml` 通過
- [ ] 7.3 實機驗證：新 session inbox 非空；`backfill --dry-run` 後三家正式回填；dream 下一輪 `atomize.slices > 0`；wake-up MOC 顯示真標題
