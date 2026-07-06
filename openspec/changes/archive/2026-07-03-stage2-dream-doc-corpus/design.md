## Context

#147（2026-06-25，archive change `2026-06-25-stage2-doc-fragment-noise-and-retitle`）已為 `classify_noise` 加入 doc-fragment 規則（`noise.py:134-157`：body 首行 heading 命中語料 heading 集合 + ≥2 內容行逐字命中）與 `instruction_corpus` 模組（bounded 探測、`corpus_for_roots` opt-in 慣例），且 `atomizer_pipeline.run` / `_promote_pass` 已有 `doc_corpus` 參數（pipeline.py:339,504）、`memory atomize` CLI 也有 `--instruction-root`（cli.py:72-75）。

漏接的只有 dream 生產路徑：`dream/cli.py:37-45` 的 `atomize_fn` 沒傳 `doc_corpus`、`memory dream run` parser（cli.py:81-89）沒有 `--instruction-root`。`noise.py:143-144` 對空 corpus 直接 `return False`，於是生產 dream loop（start.sh:195-196，每 3600s 一輪）的 doc-fragment 防線永遠關閉、`noise_dropped` 恆 0。本 change 是「把既有規則接上生產路徑」，零新判定邏輯。

## Goals / Non-Goals

**Goals:**

- `memory dream run` 提供 opt-in `--instruction-root`（repeatable），語意與 `memory atomize` 完全一致。
- dream atomize pass 收到非空語料時，doc-fragment slice 於產生端被 drop 並計入 `noise_dropped`（進 dream.jsonl 的 atomize summary，遙測恢復真實）。
- **行為契約**：不傳 `--instruction-root` 時行為與現行完全相同（空語料、規則惰性、echo slice 照舊寫入）——以測試鎖定。
- `scripts/start.sh` 生產 dream loop 傳入語料 roots。

**Non-Goals:**

- 不動 `noise.py` / `atomizer/pipeline.py` / `instruction_corpus.py`（判定邏輯與語料探測皆沿用）。
- 不清理存量 92 筆 doc-fragment（ops，不入 PR；見下方 ops 段）。
- 不動 `dream/scripts/dream-idle-wrapper.sh` 與 systemd templates（identity 路徑目前未啟用；`test_dream_systemd_template.py` 鎖定其現狀，屬另案）。
- 不動 wakeup builder / MOC builder 的讀取側排噪（audit 已標註為殘餘污染面，另案治理）。

## Decisions

### 沿用 `--instruction-root` opt-in 慣例，不做預設開啟

`corpus_for_roots(None)` 回傳空語料（`instruction_corpus.py:107-113`），規則惰性——與 `memory atomize`、`knowledge prune-noise`、`knowledge retitle-untitled` 三個既有入口一致。若改成「dream run 預設用 broad corpus」會改變所有既有呼叫者行為（含測試與手動 debug run），違反最小 diff 與行為契約。生效與否由呼叫端（start.sh）決定。

### start.sh 語料 roots 比照 `instruction_corpus.default_roots()`

傳入的 roots 為 `~/.claude/CLAUDE.md`、`~/CLAUDE.md`、`~/AGENTS.md`、`~/GEMINI.md`、`~/.codex`、`~/.gemini`、`~/.agents`、`~/prj_pri`、`~/prj_ext`（共 9 個，= `instruction_corpus.default_roots()`）。理由：

- #156 起 `moc/runner.py:21` 已用 `load_corpus()`（同一組 default roots）在 index 端 pool-exclude；產生端用同一組來源，等於「index 反正不收的就不要寫進 knowledge」，消除 wakeup brief / MOC 看得到、retrieval 看不到的不一致。
- 探測本身 bounded（depth ≤3、skip `.copilot` 等重目錄，`instruction_corpus.py:21-27`），且生產環境每輪 dream 的 moc pass 已在做同樣掃描，無新增成本量級。
- **#147 過刪教訓不適用於產生端**：broad corpus 過刪風險是針對「刪既有 knowledge」（使用者先寫筆記、後併入 AGENTS.md 的真知識 echo）；產生端 drop 只擋「新產出且逐字等於現行 instruction 文件」的 slice，該內容本來就每 session 隨 instruction 載入，drop 無資訊損失。
- roots 寫死在 start.sh（非 env var）：與該檔既有風格一致（`--promoter llm` 也是寫死），要停用可整段移除或 `PSC_DREAM_DISABLED=1`。

### `getattr(args, "instruction_root", None)` 防禦式讀取

`dream status` 子命令與既有測試建構的 Namespace 沒有此欄位；`dream/cli.py` 用 `getattr` 讀取（與 `atomizer/cli.py:107` 同式），避免 AttributeError。

### 測試策略：plumbing 單測 + identity promoter e2e

- plumbing：patch `dream.cli.atomizer_pipeline.run` 截取 kwargs，驗證有旗標→非空 `DocCorpus`（含預期 heading）、無旗標→falsy 語料。
- e2e：真 pipeline + `--promoter identity`（沿 `test_dream_e2e.py` 慣例、`_isolated_home` 隔離 HOME 避免 moc pass 掃真實家目錄），驗證帶旗標時 echo session 被 drop（`passes.atomize.noise_dropped==1`、knowledge 無該內容）且真知識 session 照常寫入；不帶旗標時 echo 照舊寫入（行為契約回歸鎖，預期改動前後皆綠）。
- start.sh 以檔案內容 guard test 鎖定（`test_dream_systemd_template.py` 同風格），防止未來重構把旗標弄掉又回到 inert。

## Risks / Trade-offs

- **產生端 drop 是不可逆的（slice 不落盤）**：誤判即損失。緩解：doc-fragment 判準是 deletion-grade 逐字比對（heading 命中 + ≥2 行逐字），#147 已以測試鎖定「編號小節單一特徵不致刪」；且 opt-in 設計讓 debug 時拿掉旗標即可重現原行為。
- **語料探測 IO 每輪多一次**：bounded walk（同 moc pass 已做的掃描），可忽略。
- **與 #177 的 `memory/cli.py` merge 衝突**：#177 會在同檔加新 subcommand。本 change 的 cli.py diff 限縮在 dream run parser 區塊（cli.py:81-89 內插一個 `add_argument`），不動 import、不動其他 parser 區塊。
- **start.sh 旗標寫死 9 行**：略冗長，但零新機制（無 env var、無 array 邏輯），guard test 鎖定內容。

## Migration Plan

1. 程式與測試落地（本 change，單一 PR）。
2. 部署：start.sh 由 repo 工作樹直接執行（dream loop 以 `PYTHONPATH="$REPO"` 跑 working tree），git pull 後重啟 start.sh（tmux 慣例：kill -TERM start.sh 再 relaunch）即生效；**非** install.sh 複製路徑，無 hooks 重新部署需求。
3. 驗證：下一輪 dream run 後 `runtime/ledger/dream.jsonl` 尾筆 atomize summary 含 `noise_dropped`（遇 doc-fragment 時 >0）；`~/.agents/log/dream.log` 可見 `atomize: dropped noise slice ...(doc-fragment)`。
4. 存量清理（ops，不入 PR）：92 筆 doc-fragment 依 #177 的固定清單路徑處理；**勿**對 serialwrap 以現行 AGENTS.md 全桶 `prune-noise`（audit 實測 manifest 會出 ~34 筆、含 mcu-flash-55 類真知識 echo）。

Rollback：revert commit 或先行從 start.sh 移除 `--instruction-root` 各行（CLI 不傳旗標即回到現行為）。

## Open Questions

1. 是否要把 dream run 的語料 roots 做成 `PSC_DREAM_INSTRUCTION_ROOTS` env？——本次不做（最小 diff）；若日後多環境需求出現再抽。
2. wakeup brief（`wakeup/builder.py:104` rglob 無排噪）與 per-project MOC 的讀取側排噪要不要補 defense-in-depth？——audit 已標註，另案。
