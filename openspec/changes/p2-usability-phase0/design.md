## Context

完整設計：`docs/superpowers/specs/2026-07-06-p2-usability-phase0-design.md`（review 修正 `f4d8862`：facade 例外條款 + R-07 正規化）。#125 Phase 0；2 PR。

## Goals / Non-Goals

**Goals:**
- `psc` 單一入口（PR-A）；env facade 消滅散落 `Path.home()` 與硬編碼（PR-B）。
- 版號治理復活（VERSION/pyproject/tag 三方一致）。

**Non-Goals:**
- repo 邊界變動（#125 Phase 1 拆包另案）。
- CLI 參數面重設計（dispatcher 零行為變更）。
- LLM 後端新功能（僅讀取集中化 + 文件）。

## Decisions

1. **`psc` 為傘狀薄 dispatcher**：只做子命令路由與 usage/exit 2，不解析業務參數、不注入預設；`python -m` 舊入口永久保留——升級零破壞。
2. **facade 是唯一 `Path.home()` 呼叫點**（review finding ④）：`paulshaclaw/config/paths.py` 集中 home 推導；其餘模組（非 tests）直接呼叫點歸零；facade 僅依賴 stdlib，禁 import 業務包（防環）。
3. **解析序 env 優先**：`PSC_MEMORY_ROOT` 等 `PSC_*` → path-split 契約預設。過渡 env（P0-1 的 `PSC_EXTRA_CORPUS_ROOT`）收編為 facade 讀點，別名保留一版。
4. **R-07 正規化比對**：tag `v0.1.0` 去 `v` 前綴後 == `VERSION` == pyproject；一致性檢查放 pytest（不加 workflow）。
5. **依賴序**：PR-A 獨立先行；PR-B 依賴 P0-1 Stage A（2 處 env 化先落）。

## Risks / Trade-offs

- 29 處機械遷移的回歸面 → 假 `$HOME` + 自訂 `PSC_*` 的 facade 單元測試 + 全套件回歸把關。
- hooks 複製部署：hook 引用 facade 時改動需重跑 install 同步（交付 checklist 載明）。
- tag 推送對外：owner 執行或明確授權後代行（R-07 禁非版本 tag）。
