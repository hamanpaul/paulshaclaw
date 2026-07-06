## Context

#125 Phase 1 拆包執行。權威設計：`docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md`（brainstorm 2026-07-06 定案 + Codex 對抗審查四項修正）。memory 對外 import 僅 `paulshaclaw.lifecycle`；主 repo 反向依賴三處（persona.contract、coordinator.manager、core.daemon）；hooks 以 `PSC_MEMORY_ROOT` 為現行契約。與 `origin/feature/p0-p3-specs`（另機開發中）協調：p1/g5/p2 是搬 code 硬前置。

## Goals / Non-Goals

**Goals:** 獨立可安裝（pipx + `hippo` CLI）、G3-aligned 常駐、單一路徑契約防 split-brain、LLM backend 三檔位、主 repo 以 SHA pin 依賴引回、15 分鐘 quickstart。

**Non-Goals:** G1–G5 實作、Phase 2 治理包拆分、PyPI 發版細節、lifecycle schema 功能演進。

## Decisions

| 決策 | 裁決 | 為什麼不是替代案 |
|---|---|---|
| 命名 | `paulsha-hippo` / CLI `hippo` | `paulsha-memory` 無識別度（#125 工作名）；海馬迴＝睡眠期記憶固化，與 dream 隱喻同構 |
| 共用件 | 先二後三：`paulsha_hippo.lib`（lifecycle/idle/jsonl）自足子 package | 獨立 `paulsha-lib` repo 多一份 conventions/CI/發版稅；子 package 自足＝升格為純機械搬移 |
| 依賴 | pip git URL **pin commit SHA**（PyPI 後轉 version+hash） | tag 可變（審查修正 #4）；file-based 零 import 需改寫 persona/coordinator 呼叫面，diff 更大 |
| 路徑 | `paulsha_hippo.paths` 單一 resolver，優先序明文（CLI > `HIPPO_*` > `PSC_*` dep. > config > 預設） | 雙前綴並存不定序＝hooks 寫 A 根、dream 讀 B 根的靜默分家（審查修正 #1） |
| 常駐 | `hippo install service`：systemd 偵測 + `dream supervise` fallback | systemd-only 牴觸 G3「先驗證再選路」，且 start.sh:214 現有 supervisor 迴圈依賴 memory CLI（審查修正 #2） |
| daemon | agent argv 改 daemon 自有 config | `resolve_command_argv` base_dir 安裝後＝site-packages，相對路徑必壞（審查修正 #3） |
| 歷史 | template 全新開始 | filter-repo 需逐 commit 除污審查，成本高且有殘留風險 |

## Risks / Trade-offs

- [move-vs-modify 與 p1/g5/p2 衝突] → 該三件落地後才搬 code（tasks 有 gate task）。
- [字串級隱藏耦合] → 抽離 PR 全 repo grep `paulshaclaw.memory` 清零。
- [deident 殘留（R-21/#201）] → 新 repo deident gate day-1，公開前 sanitize。
- [發版鎖鏈] → SHA pin + protected tags + CI 可重現安裝。

## Migration Plan

1. 先行（不搬 code）：hippo repo 骨架（template、CI 四道、README 草稿）。
2. 閘後：code 遷移 → 主 repo 遷移 PR（依賴+import+cutover 同 PR）→ consumer tests 綠 → start.sh 回滾點保留一版。
3. 回滾：還原 start.sh dream 段 + revert 遷移 PR + pip 移除 hippo（`~/.agents/memory` 資料不動故可逆）。

## Open Questions

- hippo repo 首版 semver 起點（0.1.0 vs 沿 stage2 演進脈絡）——建 repo 時定。
- stage2-* 12 份 specs 遷入 hippo 後，主 repo archive 的保留形式（tombstone vs 全刪）——遷移 PR 時定。
