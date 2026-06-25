# Stage 2 promoter 噪音治理設計

> 日期：2026-06-25 ｜ 來源：brainstorming（#139 P2）
> 配對：#139 P0/P1（frontmatter escaping + 韌性）已於 #141 merge；本文件處理 P2 品質段。

## 1. 背景：證據

對 live store `~/.agents/memory` 評估，knowledge 553 個非-moc slice 中：

- **474（86%）為結構/空殼噪音**。
- 218（39%）正文 < 40 字（空殼）。
- 26 張含「尚未收到您的具體需求」placeholder。
- 真正 distilled 原子僅十餘張。

噪音的精準訊號（取樣實據）——slice 的 **body 是 importer `render_markdown` 的結構段落 echo**：

| slice | atom_title | body |
|---|---|---|
| `cwd--` | cwd | `## CWD\n/home/paul_chen` |
| `prompts--` | prompts | `## Prompts\n- (none)` |
| `source--` | source | `## Source\n- Tool: ... - Session: ... - Raw payload: ...` |
| `touched-files--` | touched-files | `## Touched files\n- (none)` |
| `summary--` | summary | `## Summary\n使用者招呼與啟動 session` |
| `untitled--` | untitled | `## 動工前\n- [ ] 確認當前分支...`（321 字，真實 checklist） |

關鍵：`untitled--` 雖 title 生成失敗，body 卻是真內容 → 應**保留**（title 是另一個品質問題）。因此判準**以 body 內容為準**，與 atom_title / project 無關。

噪音來自 importer 把每個 session 渲染成含 `## Summary / ## Source / ## CWD / ## Touched files / ## Referenced artifacts / ## Prompts` 的結構文件，splitter 依 heading 切成 fragment，promoter（identity 遺留 + gemma4 偶發 echo）把結構段落各自原子化成 knowledge slice。

## 2. 目標與範圍

- **產生端**：修 pipeline 使結構段落 echo、空殼、placeholder 不再寫進 knowledge。
- **回溯端**：清掉既有 474 張噪音，使 wake-up MOC 立即乾淨。
- 不動 raw archive / inbox（source session 為真相源，永遠保留）。

**不在範圍**：splitter 層跳過結構段落（未來最佳化，省 LLM 呼叫）；title 重生、project 重解析（untitled / no-project 的品質問題，另案）；promoter prompt 調校。

## 3. 決策（brainstorming 拍板）

| 決策 | 選擇 | 理由 |
|---|---|---|
| 範圍 | 產生端 + 回溯清理 | 只修產生端 → 舊噪音永遠卡 MOC；只清理 → 新噪音續生。一次根治。 |
| 回溯處置 | **hard delete + manifest** | source session 在 archive 當真相源、產生端修好後不再生 → 安全；manifest 供稽核。 |
| 判準精度 | **以 body 內容為準** | 只刪結構 echo / 空殼 / placeholder；untitled / no-project 若 body 有真內容則保留，不誤刪。 |
| `## Summary` | 列入 structural-echo | importer 模板的 1 行 session 描述、非知識。 |

## 4. 方案

採 **Approach A：共用 classifier + 產生端 skip + 一次性 prune CLI**。

- 一個 `classify_noise` 模組作判準單一真相源，產生端與回溯端共用 → DRY、同時擋 identity 遺留與 gemma4 echo。
- 否決 Approach B（根部修 splitter/importer：耦合 importer 模板、抓不到 LLM echo、回溯仍須另寫）。
- 否決 Approach C（只在 MOC 表面隱藏：與 hard delete 決策不符）。

## 5. 架構與單元

### ① noise classifier（單一真相源）

新模組 `paulshaclaw/memory/noise.py`，純函式、無 IO：

```python
classify_noise(frontmatter: dict, body: str) -> NoiseVerdict(is_noise: bool, reason: str)
```

判準（依序，命中即回 is_noise=True）：

1. **structural-echo**：body strip 後**第一行**為 importer 結構 heading 之一——
   `## CWD` / `## Source` / `## Prompts` / `## Touched files` / `## Referenced artifacts` / `## Summary`
   （reason=`structural-echo:<section>`）。判定僅看第一行 heading，不需推斷段落範圍，
   對得上實據（`## CWD\n/home/...`、`## Prompts\n- (none)`、`## Summary\n使用者招呼...`）。
2. **placeholder**：body 含 `(無內容)` / `尚未收到您的具體需求` / `目前尚未收到`，或本體僅 `- (none)` / `(unknown)`（reason=`placeholder`）。
3. **empty**：body 去除標題行（`#`..）與空白行後無實質內容（reason=`empty`）。涵蓋真正空白與**純標題片段**（如 `# Session <uuid>`，46 字）。**MUST NOT 以字元長度門檻判定。**
4. 其餘 → is_noise=False（含 `untitled--` 真內容、短但真實 fact）。

> **設計修正（2026-06-25，實作中發現）**：原訂 `empty = body < 40 字` 在產生端會誤刪真實短內容（30 字 CJK 真結論），且因 `# Session <uuid>` 為 46 字反而漏抓。改為 content-based「只剩標題/空白」後，live 實測 noise 命中由 831（含 9 誤刪風險）升為 988（hollow 166 全為純標題片段），零誤刪——更忠於「以內容為準、不誤刪」。

classifier 只看 `body`（與 frontmatter 的 atom_title/title/project 解耦），確保「以內容為準」。

### ② 產生端整合（防新生）

`paulshaclaw/memory/atomizer/pipeline.py::_promote_pass`：
- promote 後、`slice_frontmatter.validate` 通過後，對每個 slice 跑 `classify_noise(slice_.frontmatter, slice_.body)`。
- is_noise 者：不寫入 knowledge、不 append semantic edge，計入 `summary["noise_dropped"]`，append warning（附 slice_id + reason）。
- fragment 照常 archive（source 不丟）；session 仍標記 promoted（避免下輪重跑）。
- dry-run 分支同步套用（計數一致）。

### ③ 回溯端（清既有）

新 CLI 子命令 `psc memory knowledge prune-noise`（`paulshaclaw/memory/cli.py` + 對應 handler）：
- 預設 `--dry-run`：掃 `knowledge/**.md`（排除 `*-moc.md`），對每檔 `read` frontmatter+body 跑 classifier，輸出將刪清單與 reason 統計，不動檔。
- `--apply`：hard delete 命中檔；最後呼叫既有 `moc_builder.build_mocs` 重建。
  - ledger 不需主動移除：`moc_builder._active_slices` 只迭代**現存** `knowledge/**.md`，刪檔後該 slice 自然不入 MOC；relations/retrieval 中的 dangling slice_id 變 inert，不影響正確性（避免改 append-only ledger 的額外複雜度）。
- 一律輸出 manifest `runtime/ledger/prune-<now>.jsonl`（每行：slice_id / project / path / reason）。
- `--memory-root` 與 `--now` 沿用既有 dream CLI 慣例（避免 `Date.now()` 不可測）。

### ④ 資料流

```
[產生端]  session → split → fragments → promoter → slices
                                              │
                                   classify_noise(body)
                                         ├─ noise → drop + warn + noise_dropped++
                                         └─ clean → write knowledge + relations

[回溯端]  knowledge/**.md → read(fm,body) → classify_noise(body)
                                         ├─ noise → (apply) hard delete + ledger 移除 + manifest
                                         └─ clean → 保留
                                   → build_mocs 重建
```

## 6. 錯誤處理

- prune `--apply` 對單檔刪除失敗：記 manifest（status=error）、跳過該檔、續跑其餘（per-file 隔離，沿用 #141 韌性原則）。
- classifier 對畸形 frontmatter：由 `frontmatter_io.read` 容錯（#141 已修）回 `({}, body)`，classifier 仍可判 body。
- 重建 MOC 失敗不影響已完成的刪除（manifest 已落地）。

## 7. 測試（TDD）

- **classifier 單元**：6 結構 echo（含 Summary）+ 空殼 + 3 種 placeholder 判 noise；`untitled--` 真 checklist body / 短但真實 fact 判非 noise（精度防誤刪）。
- **產生端**：含結構 fragment 的 session → knowledge 僅留真原子、`noise_dropped` 計數正確、source fragment 仍 archive。
- **prune CLI**：dry-run 不動檔且統計正確；`--apply` 刪正確檔、好 slice 全留、ledger 移除、manifest 內容正確；重建後 MOC 不含已刪 slice。

## 8. 部署順序

1. merge 產生端 + classifier + prune CLI（含測試）。
2. 部署（`git pull` main；dream loop 下個 tick 自動用新碼，新 session 不再生噪音）。
3. 本機 `prune-noise --dry-run` 過目清單。
4. `prune-noise --apply` 清既有 474 → 重建 MOC → 確認 wake-up 乾淨。

## 9. 驗收

- [ ] classifier 對六類結構 echo + 空殼 + placeholder 全判 noise；untitled 真內容判非 noise。
- [ ] 產生端 dream run 後 knowledge 不再出現結構 echo slice；`summary.noise_dropped` 反映過濾數。
- [ ] `prune-noise --apply` 後 knowledge 噪音占比由 ~86% 降至個位數；好 slice（如 `versioning-and-release-policy`）全留；manifest 完整。
- [ ] wake-up MOC 不再被結構欄位卡與空殼洗版。

## 10. Adversarial-review 硬化（2026-06-25，Codex challenge review 後）

Codex 對抗式 review 提三項，皆已修（TDD）：

- **[finding 1] 噪音丟棄汙染 dream 健康狀態**：原本每筆 noise 丟棄 append 進 `warnings`、`run()` 以 `skipped=len(warnings)` 計，使正常過濾被 dream orchestrator 判為 `partial`。改為 noise 丟棄只計 `summary.noise_dropped` + `LOGGER.info`，不進 `warnings`/`skipped`；健康訊號保留給真異常。
- **[finding 2] prune 先刪後寫 manifest**：`--apply` 改為先持久化 planned manifest → 再 unlink → atomic replace 重寫 final 狀態。任一後續失敗都不致留下無紀錄刪除。
- **[finding 3] body-only classifier 誤刪風險**：structural-echo 加「散文行 ≤1」限制（避免誤刪以 `## Summary` 開頭但有多段真內容的筆記）；placeholder 改為「開頭前 12 字內」偵測（避免誤刪引用該字串的真筆記）。live 實測命中 988→946，仍零真內容誤刪。
