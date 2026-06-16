# Copilot Brief — Stage 2 內容擷取 Phase 1

> 給 GitHub Copilot CLI 冷啟動執行用。把下方 fenced block 整段貼進 Copilot pane，或直接叫 Copilot 讀本檔。

## 要餵給 Copilot 的計畫（唯一事實來源）

```
docs/superpowers/plans/2026-06-16-stage2-content-extraction.md
```

這份 plan 有 8 個 task 群、每步都附**完整 code 與 fixture**、TDD red/green/commit 結構。Copilot 逐 task 照做即可。背景設計與規格：

- 設計：`docs/superpowers/specs/2026-06-16-stage2-content-extraction-design.md`
- 規格：`openspec/changes/stage2-content-extraction/`

## 貼給 Copilot 的指令

```
任務：實作 Stage 2 記憶內容擷取 Phase 1，依既定 TDD 計畫逐 task 執行。

Repo：/home/paul_chen/prj_pri/paulshaclaw
Branch：feature/stage2-content-extraction（已有 spec/openspec/plan 三個 doc commit；
        在此 branch 的 worktree 上加實作 commit）

唯一事實來源（逐 task 照做，每步都附完整 code，照抄即可）：
  docs/superpowers/plans/2026-06-16-stage2-content-extraction.md
背景設計：docs/superpowers/specs/2026-06-16-stage2-content-extraction-design.md
規格：    openspec/changes/stage2-content-extraction/

執行規則：
1. 嚴格 TDD：每 task 依序 red（寫失敗測試→跑確認 FAIL）→ green（最小實作→跑 PASS）→ commit。
2. 測試一律 `python3 -m pytest <path> -q`，從 repo root 跑。
   ※ repo 的 .venv 沒裝 pytest，別用；系統 python3 有 pytest 9.x。
3. 每個 task 群一個 commit；conventional commit，訊息用繁體中文（本 repo 屬 hamanpaul → zh-tw）。
4. 最小 diff，只動計畫列出的檔案。
5. 套件是 `pip install -e` editable，改 `paulshaclaw/` 即生效——
   **不要動** `~/.agents/memory/hooks/` 的部署副本、不要重跑 install.sh。
6. 範圍只到 Phase 1（計畫 Task 1–8）。**不要做 Phase 2**（promoter→LLM 蒸餾）。
7. Task 6（projects.yaml）是 `~/.agents/config/` 設定檔、不進 repo commit——照計畫補登＋驗證即可。
8. 全 task 完成後跑 `python3 -m pytest paulshaclaw/memory/tests/ -q` 確認全綠
   （`test_atomizer_llm_live` 會 skip，正常）。回報結果。
   **不要 merge、不要 push 到 main**；要不要開 PR 等指示。

幾個計畫已寫但容易踩的點：
- 標題注入點＝`title.apply` 設 `session["assistant_summary"]`，位置在 pipeline.py 的
  `_preview_queue_item_unlocked` 內、`render_markdown` 之前（line 239 後）。
- gemma4 :8001 目前離線——title 測試用 mock runner；實機會走 fallback，屬正常。
- codex prompts 從 rollout 是 best-effort，缺檔留空、不報錯。
```
