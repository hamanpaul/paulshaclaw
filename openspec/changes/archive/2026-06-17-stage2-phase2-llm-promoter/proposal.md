## Why

Stage 2 Phase 1 補實了內容擷取與 per-session 標題，但知識層仍是 `promoter: identity`——把 session 依 heading 切成 per-fragment「facet 切片」，無語意合併、無關聯。LLM 蒸餾料件（`LLMPromoter`、`prompt.py`、`llm_output.py`、`agent_exec.py`、種子 skill）早在 2026-06-02 就接好線但實機從未啟用。真正的開關在 `scripts/start.sh:195` 寫死的 `--promoter identity`。Phase 2 翻開它，讓知識層升級為可驗證、可重用的語意原子（Zettelkasten）。

## What Changes

- **forward-only canary（Phase 2a）**：翻 `scripts/start.sh:195` dream loop `--promoter identity` → `--promoter llm`，新進 session 走 LLM 原子蒸餾；舊 451 條 identity slice 暫不動。
- **輸出 token 窗 env override**：`AgentExecClient` 加 `env` 覆寫能力，atomize 呼叫設 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`（預設 8192、config 可調），避免多原子 JSON 被 `claude-gemma4` 的 1024 預設截斷 → fail-closed 永卡。
- **雙層 MOC**：MOC builder 階層化，per-session 標題當主脊、靠 `source_session`（即 `distilled_from` 在 frontmatter 的物化形式）反查掛該 session 蒸出的原子；**相容混血**（無原子的 session 只顯示標題）。
- 非破壞：沿用既有 fail-closed、LLM 輸出 cache 凍結、Stage 3 schema 不變、splitter/ledger 骨架不動。

**本 change 範圍＝Phase 2a（canary 啟用）。** 全量回填重蒸餾（Phase 2b）明確**留給後續獨立 change**：canary 由人工判過關後，先實測確認 janitor 真在跑、再對 archived session 重蒸餾並讓舊 identity slice decay。

## Capabilities

### New Capabilities
- `stage2-llm-distillation`: LLM promoter 對單一 session 的語意原子蒸餾契約——per-session promote、輸出窗 sizing 與 fail-closed、forward-only canary 遷移語意（identity/llm 混血相容）、以及蒸出原子在 MOC 的雙層階層呈現。（全量回填重蒸餾留給 Phase 2b 後續 change。）

### Modified Capabilities
<!-- 無既有 requirement 釘住 promoter 模式或 MOC 階層；Phase 1 的 stage2-session-content 要求不變。 -->

## Impact

- **程式**：`paulshaclaw/memory/atomizer/agent_exec.py`（env 覆寫）、`config.py` + `atomizer.yaml`（`agent_exec.max_output_tokens`）、`cli.py`（`_build_promoter` 組 env）、`memory/moc/moc_builder.py`（雙層階層）。
- **運維**：`scripts/start.sh:195`（翻 `--promoter llm`，重啟生效）。LLM 路徑 `claude-gemma4`→proxy:18080→gemma4@192.168.199.199。
- **資料**：知識層由 identity facet 收斂為 LLM 原子（Phase 2b）；processing ledger 開始記 `promoter=llm`/`model`/`skill_hash`。
- **依賴**：gemma4 backend 常駐；fail-closed 確保斷線只是下輪重試、不掉資料。
- **不影響**：Stage 3 schema、splitter/ledger/pipeline 骨架、hook entry 檔、retrieval（Topic 7）、全域實體圖與 SkillOpt（後續）。
