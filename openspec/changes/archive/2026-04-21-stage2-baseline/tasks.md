> Stage 2 baseline 為 reverse-record change：Stage 2 spec/docs 實作已於 merge commit `2da5ccb` 合併到 main。下列任務為對照已落地工作驗證 spec 成立的反向檢核。

## 1. 路由與事件 baseline

- [x] 1.1 確認 `openspec/specs/stage2/scope.md` §2 含 `inbox -> work-centric -> knowledge` 全字串且三層各自有約束
- [x] 1.2 確認 §3 含 `decayed/reactivation` 並描述兩事件的條件與動作
- [x] 1.3 確認 `paulshaclaw/memory/routing.md` 有 source→initial landing→upgrade→target 四欄對應表

## 2. janitor / replay 邊界

- [x] 2.1 確認 `paulshaclaw/janitor/service.md` 宣告 janitor 為獨立服務，含 systemd 單位建議
- [x] 2.2 確認 scope §4 或 routing.md 宣告 replay 只讀 distilled artefact 與 ledger 事件

## 3. sync-back gate baseline

- [x] 3.1 確認 `custom-skills/paulsha-memory/README.md` 列 5 條 sync-back gate 條件
- [x] 3.2 確認 scope §5 item 4 具體列出 `slice_id / artifact_kind / supersedes / checksum` 四個 Stage 3 frontmatter 欄位

## 4. Integration 驗證

- [x] 4.1 `bash paulshaclaw/memory/tests/stage2_integration_check.sh` 於 main 跑出 7 條 PASS 並以 `[stage2] ok` 結尾
- [x] 4.2 code review item 5 於 fixup commit `6cc4356` 修復，7/7 項目全 PASS

## 5. 文件 baseline

- [x] 5.1 確認 `docs/superpowers/workstreams/stage2-paulsha-memory/` 含 plan/task/todo/review 與 `evidence/{README,stage2-integration-template}.md`
- [x] 5.2 確認 `docs/superpowers/archive/stage2-paulsha-memory-*.md` 存在

## 6. Archive readiness

- [x] 6.1 `openspec validate stage2-baseline --strict` 通過
- [x] 6.2 `openspec archive stage2-baseline --yes` 同步 delta 至 `openspec/specs/stage2-memory-governance/spec.md`
