## Context

Phase 0（archived `2026-06-18-persona-phase0-config-loader`）已交付 config-driven catalog：`loader.load_catalog()` 從 `personas.yaml` 載入 `dict[str, PersonaContract]`，`contract.PERSONA_CATALOG` 為其預設。`guardrail.PersonaGuardrail(catalog).evaluate_filesystem(role=, path=)`、`context.build_persona_context(role=, catalog=, overlay=)`、`contract.validate_handoff_message(payload, catalog=)` 皆可直接 reuse。但 persona 仍無 runtime 消費者。

Phase 1（設計 §11）要把三個強制點的**觀測形狀**接出，沿用 Stage 2 promoter 的 shadow→enforce canary：shadow 恆放行、只輸出 verdict；調至零誤殺後翻 enforce。本 change 為三個 building block（manifest 讀寫、contract render、shadow diff-gate CLI），不接 coordinator（Phase 2）、不建 CI（Phase 3）。

## Goals / Non-Goals

**Goals:**
- `handoff.py`：`runtime/handoff/<slice_id>.json` 的 write/read，read 經 `validate_handoff_message` 驗證、非法 raise `ValueError`、缺檔 fail-closed。
- `render.py`：`render_contract_prompt(role)` 輸出確定性 prompt 前言（① contract 注入），reuse `build_persona_context`，未知 role raise `ValueError`。
- `gate.py`：薄 CLI，`git diff --name-only base...head` 逐檔 `evaluate_filesystem` + 驗 manifest，輸出 JSON verdict；**預設 shadow 恆 exit 0**，`--enforce` 時違規 exit 1。邏輯放函式、`main(argv)` 薄殼以利測試。
- 既有 stage4 / loader 測試維持綠；新測試覆蓋四類情境。

**Non-Goals:**
- ② 的角色不變式（reviewer diff 不可含 code、builder 須帶測試）細則——本 change 只做 path-scope + manifest 驗證；不變式留後續 enforce 強化。
- coordinator dispatch 接線（Phase 2）、`persona-scope.yml` CI 硬後盾（Phase 3）、fan-out（Phase 4）。
- 真正翻 enforce 的決策（須先 shadow 跑真 PR 調誤殺）；本 change 只提供 `--enforce` 旗標機制。

## Decisions

- **D1 — manifest fail-closed 與驗證委派**：`read_manifest(path)` 先檢查檔案存在（缺檔 raise，fail-closed 呼應 loader 慣例），讀 JSON 後委派 `contract.validate_handoff_message`；`result.ok` 為 false → raise `ValueError`（附 `result.errors`）。`write_manifest` 僅負責序列化＋`mkdir -p` 父目錄，不在寫入時驗證（寫入端責任在呼叫者；read 端 fail-closed 為信任邊界）。理由：read 是 CI/gate 的信任邊界，集中驗證最穩。
- **D2 — render 確定性**：`render_contract_prompt` 以 `build_persona_context` 的 `role`/`allowed_phases`/`write_paths`/`effective_tools` 組多行字串，欄位以 `sorted`/穩定序輸出（effective_tools 已被 context 排序；write_paths/allowed_phases 維持契約宣告序），確保同輸入同輸出（可進 prompt cache、可斷言）。未知 role 由 `build_persona_context` 既有 `raise ValueError` 自然冒泡。
- **D3 — gate 邏輯/殼分離**：`compute_changed_paths(base, head, repo=None)`（呼 `git diff --name-only base...head`）、`evaluate_diff(role, changed_paths, catalog)`、`load_manifest_ok(role, manifest_path, catalog)`、`build_verdict(...)` 為純函式；`main(argv)` 解析參數、組 verdict、`print(json.dumps(...))`、依模式回 exit code。測試以 monkeypatch `compute_changed_paths` 或 temp git repo 注入 diff，免依賴真 PR。
- **D4 — shadow vs enforce 退出碼**：`build_verdict` 算 `ok = (not violations) and handoff_ok`。`main` 預設（無 `--enforce`）**恆 return 0**（observe/log，呼應 §5 shadow）；`--enforce` 時 `0 if ok else 1`。verdict JSON 一律輸出（兩模式都印），差別只在退出碼。
- **D5 — catalog 來源**：gate 用 `loader.load_catalog()`（不直接吃 `PERSONA_CATALOG`，與設計 §8「CI 讀 manifest from_role + 跑 gate」一致，且便於日後路徑覆寫）。handoff/render 預設 `catalog=None` → 落到既有預設（`validate_handoff_message`/`build_persona_context` 內部回退 `PERSONA_CATALOG`）。

## Risks / Trade-offs

- [manifest 信任：CI 讀 `from_role` 決定 scope] → 本 change 只做機制；惡意改 manifest 降權由「manifest 路徑屬 manager scope、改它即越界」緩解（設計 §6/§13），enforce 階段強化。
- [`git diff base...head` 在淺 clone / 無共同祖先時行為] → 測試以 temp git repo 建真 merge-base 驗證；gate 對 diff 失敗（非零 returncode）採 fail-closed（視為無法驗證 → violations 記一筆 or raise），避免 shadow 階段假綠。
- [render 字串格式日後變動破壞斷言] → 測試只斷言「含 role 名與各 write_path 子字串」而非全文比對，降低脆性；確定性由 D2 結構保證。
- [shadow 恆 exit 0 可能掩蓋真違規] → 正是 shadow 設計意圖（先觀測）；verdict JSON 仍完整輸出供人/log 檢視，翻 enforce 為獨立決策。
