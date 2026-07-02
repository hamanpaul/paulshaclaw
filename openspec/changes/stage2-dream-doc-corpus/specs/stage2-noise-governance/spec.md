# stage2-noise-governance

dream 生產路徑接上既有 doc-fragment 語料（#176）：`memory dream run` 提供 opt-in `--instruction-root`，atomize pass 下傳 `doc_corpus`；生產 dream loop（start.sh）傳入語料。零新判定邏輯。

## MODIFIED Requirements

### Requirement: 產生端與回溯 prune 共用 doc-fragment 判準

atomize 的 promote pass 與 `psc memory knowledge prune-noise` SHALL 自 instruction-doc 語料來源組裝 `doc_corpus` 並傳入 `classify_noise`，使 doc-fragment 於產生端被阻斷新生、於回溯 prune 被清除。語料探測 SHALL 邊界化（限定安全 root、限深、skip 重目錄），探測不到語料時 doc-fragment 規則惰性而不致誤刪。

`memory dream run` SHALL 提供 opt-in、repeatable 的 `--instruction-root` 參數（語意與 `memory atomize` 既有參數一致），並以 `corpus_for_roots` 組裝 `doc_corpus` 傳入 atomize pass，使 doc-fragment 規則在 dream 生產路徑生效、drop 計入 atomize summary 的 `noise_dropped`（隨 dream ledger 記錄）。未傳 `--instruction-root` 時 SHALL 組出空語料、doc-fragment 規則惰性，dream run 行為 MUST 與既有行為完全一致（行為契約）。生產 dream loop（`scripts/start.sh`）SHALL 對 `memory dream run` 傳入 instruction-doc 語料 roots，其來源 SHALL 與檢索 index 端 pool-exclude 所用的 curated default roots（`instruction_corpus.default_roots()`）一致，使產生端 drop 與 index 端排除的判定語料相同。

#### Scenario: 回溯 prune 清除 doc-fragment

- **WHEN** 對含 instruction 文件碎片與真知識的 knowledge 執行 `prune-noise --apply`，且語料涵蓋該 instruction 文件
- **THEN** doc-fragment 碎片 SHALL 被 hard delete、真知識 SHALL 全數保留、manifest SHALL 記錄每筆刪除（reason `doc-fragment`）、MOC SHALL 重建且不含已刪 slice

#### Scenario: 產生端阻斷 doc-fragment 新生

- **WHEN** promoter 對某 session 產出一個 body 為 instruction 文件逐字章節的 slice，且產生端已組裝涵蓋該文件的語料
- **THEN** 該 slice MUST NOT 寫入 knowledge 層、SHALL 計入 `noise_dropped`，source fragment SHALL 仍被 archive

#### Scenario: dream run 帶 --instruction-root 時 doc-fragment 於 dream 路徑被 drop

- **WHEN** 執行 `memory dream run --instruction-root <doc>`，inbox 含一個 body 為該 instruction 文件逐字段落（heading 命中 + ≥2 內容行逐字命中）的 session 與一個真知識 session
- **THEN** doc-fragment slice MUST NOT 寫入 knowledge 層、dream 結果 `passes.atomize.noise_dropped` SHALL 計入該筆，真知識 slice SHALL 照常寫入 knowledge

#### Scenario: dream run 不帶 --instruction-root 時行為不變

- **WHEN** 執行 `memory dream run`（未傳 `--instruction-root`），inbox 含 body 為 instruction 文件逐字段落的 session
- **THEN** doc-fragment 規則 SHALL 惰性（`noise_dropped` 不因該 slice 增加）、該 slice SHALL 照既有行為寫入 knowledge——與變更前行為完全一致

#### Scenario: 生產 dream loop 傳入語料 roots

- **WHEN** 檢視 `scripts/start.sh` 的 dream loop 對 `memory dream run` 的呼叫
- **THEN** 該命令 SHALL 帶 `--instruction-root` 參數，且 roots 集合 SHALL 與 `instruction_corpus.default_roots()` 一致
