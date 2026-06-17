## Context

Stage 2 知識層目前 `promoter: identity`：session 依 heading 切 fragment、1:1 產 facet slice，無語意合併/關聯。LLM 蒸餾料件 2026-06-02 就接好線（`LLMPromoter`、`agent_exec.py`、種子 skill、CLI `_build_promoter` 在 `promoter: llm` 時組出完整管線）但實機從未跑過。真正開關在 `scripts/start.sh:195` 寫死的 `--promoter identity`。

LLM 路徑：`AgentExecClient`（stdin 餵 prompt）→ `scripts/claude-gemma4`（headless claude）→ proxy `:18080` → gemma4 `gemma4-26b-a4b-nvfp4` @ 192.168.199.199（常駐）。fail-closed 與 LLM 輸出 cache 凍結已內建。

完整 brainstorm 設計：`docs/superpowers/specs/2026-06-17-stage2-phase2-llm-promoter-design.md`。

## Goals / Non-Goals

**Goals（本 change＝Phase 2a）：**
- forward-only canary：翻 `start.sh` 為 `--promoter llm`，新進 session 走 LLM 原子蒸餾。
- atomize 輸出窗 env override，避免 1024 預設截斷 JSON。
- 雙層 MOC（session 標題 + `source_session` 反查掛原子），相容 identity/llm 混血。

**Non-Goals（明確排除）：**
- **全量回填重蒸餾 + janitor decay 收斂 → Phase 2b 後續獨立 change**（canary 人工判過關後才動）。
- 跨 session 全域實體圖（Topic 5）、SkillOpt 迴圈、Topic 7 retrieval。
- 改 Stage 3 schema、splitter/ledger/pipeline 骨架、hook entry 檔。
- Phase 2 的 relations 僅限 per-session batch（`relates_to` + `mentions`）。

## Decisions

1. **分段 forward-only canary → 全量回填**（而非一次全量）。先低風險翻開關試水，種子 skill 從未在真 gemma4 跑過，canary 先暴露品質問題；過關才補全量回填取代舊 451 條。canary 判準留 judgement call。
   - 替代：一次性全量 + snapshot 回滾——快但品質不均、依賴 snapshot 而非逐條驗證；否決。
2. **輸出窗在 atomizer subprocess env 設大**（決策 A）。`AgentExecClient` 加 `env` 參數，`subprocess.run(env={**os.environ, **env})`；`config.agent_exec.max_output_tokens` 預設 8192、可調；CLI 組成 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`。gemma4 256k context 吃得下輸入；輸出 8192 足夠最大 session（~10 原子）且不 runaway。
   - 替代：改 `claude-gemma4` 全域預設——會影響 bro 短聊；否決。專用 agent command 變體——多一層設定，無必要；否決。
3. **雙層 MOC 相容混血**。builder 階層化但不假設全有原子；無 `distilled_from` 原子的 session 退化為只顯示 per-session 標題，canary 期間 identity/llm 並存不報錯。
4. **gemma4 可用性靠既有基礎建設**，不另建 24x7 service：backend 常駐、生命週期跟 `start.sh`、claude-gem 可由 `/agent %x start` 拉起；fail-closed 兜底。

## Risks / Trade-offs

- **R1 輸出截斷 → session 永卡 split** → 決策 A：env 設 8192（可再調）。
- **R2 janitor 未必真 decay 舊 identity slice** → Phase 2b 硬前提，先實測 dream loop 是否帶起 janitor、content-derived slice_id 變動後是否判 stale；未涵蓋則補路徑。
- **R3 canary 期 MOC 混血** → 雙層 builder 相容兩態。
- **品質未驗** → 種子 skill 靠 forward-only canary 暴露問題，SkillOpt 留後續。
- **回填覆寫** → `--dry-run` + 可重入 + canary 過關後才動。

## Migration Plan

本 change（Phase 2a）：
1. 改 atomizer env/config/CLI + 雙層 MOC builder（套件內，下次 dream 即生效）。
2. 翻 `start.sh:195` `--promoter llm`，重啟 start.sh → 啟動 canary。
3. canary：人工讀新 session 原子品質 + 看 fail-closed 率；judgement call。
- **回滾**：start.sh 改回 `--promoter identity`；新 LLM 原子內容派生 slice_id，停用後不再產生，既有原子留存。

後續（Phase 2b 獨立 change）：canary 過關 → 確認 janitor → 跑 backfill 重蒸餾 → 舊 identity slice decay。

## Open Questions

- （Phase 2b 再解）janitor 是否已在 dream loop 內跑、是否會 decay 因 slice_id 改變而 stale 的舊 identity slice；backfill 是獨立 CLI 子命令或擴充現有入口。
