## 1. 先行（不搬 code，不必等閘）

- [ ] 1.1 依 new-project-template 建立 `hamanpaul/paulsha-hippo` repo（無歷史、conventions 1.0.12、R-20 版本同步、protected tags）
- [ ] 1.2 hippo CI 四道骨架：tests（R-19）、policy-check、`paulsha_hippo.lib` import-lint（禁內部依賴）、deident gate（#201）
- [ ] 1.3 hippo README 草稿（zh-tw：定位→quickstart→安裝→設定→日常使用→架構→家族關係）
- [ ] 1.4 #125 issue comment 註記工作名更名 `paulsha-memory` → `paulsha-hippo` 與本 change 連結

## 2. 動工閘（gate，全綠才進入 §3）

- [ ] 2.1 確認站穩閘 G1–G5 全綠（#14/#124/#126/#132/#128 CLOSED）+ 2 週穩定觀察期
- [ ] 2.2 確認 `p1-memory-three-gaps`、`g5-hook-install`、`p2-usability-phase0` 已 merge（move-vs-modify 前置）

## 3. hippo 程式碼遷入

- [ ] 3.1 `memory/**` 平移為 `paulsha_hippo/`；`lifecycle/**` + `dream.idle` + ledger jsonl 原語重組為 `paulsha_hippo.lib.{lifecycle,idle,jsonl}`；87 個 test 檔隨遷
- [ ] 3.2 `paulsha_hippo.paths` 單一權威 resolver（優先序：CLI 旗標 > `HIPPO_MEMORY_ROOT` > `PSC_MEMORY_ROOT`（deprecated 警告）> config.yaml > `~/.agents/memory`）+ `config.py`（單一檔 + `HIPPO_*` 覆寫 + secret.env 規則）
- [ ] 3.3 CLI `hippo` 命令樹（`[project.scripts]`；init/atomize/dream/janitor/replay/bundle/search/wakeup/syncback/knowledge）
- [ ] 3.4 蒸餾 backend 三檔位：`claude-headless` preset、`openai-compatible` http-runner、`custom-argv`（統一 runner 介面）；claude-gemma4 wrapper 移入 `examples/`
- [ ] 3.5 `hippo install hooks`（吸收 g5 冪等 + verify）與 `hippo install service`（systemd 偵測→user units；不可用→指引 supervise）+ `hippo dream supervise` + `hippo doctor`（含雙 root FAIL 檢查）
- [ ] 3.6 `openspec/specs/stage2-*` 12 份 capability specs 遷入 hippo openspec
- [ ] 3.7 hippo 全測試綠 + 15 分鐘 quickstart 實走（乾淨環境：pipx 安裝→init→匯 transcript→dream run→wakeup）

## 4. 主 repo 遷移（單一 PR，含回滾點）

- [ ] 4.1 刪除 `paulshaclaw/memory/**`、`paulshaclaw/lifecycle/**`；pyproject 加 SHA pin 依賴
- [ ] 4.2 import 改寫：persona.contract → `paulsha_hippo.lib.lifecycle`；coordinator.manager → `paulsha_hippo.lib.idle`
- [ ] 4.3 `core/daemon.py` 解耦：`/agent` argv 改 daemon 自有 config（絕對路徑），缺設定時明確報錯不靜默 fallback
- [ ] 4.4 `scripts/start.sh` dream 段 cutover：PATH 偵測呼叫 `hippo dream supervise`，未裝則跳過+警告；deploy planner 移除 dream unit
- [ ] 4.5 `psc` CLI memory 子樹移除（錯誤訊息指引 `hippo`）；全 repo grep `paulshaclaw.memory`/`paulshaclaw.lifecycle` 字串清零
- [ ] 4.6 consumer tests：(a) hippo installed 且無 `paulshaclaw.memory` 時 `/agent start/status` 綠 (b) 舊 `PSC_*` hooks 與 hippo 服務同 root (c) systemd-unavailable fallback 可用；import 面 CI 檢查（僅允許 `paulsha_hippo.lib.*`）
- [ ] 4.7 CLAUDE.md／README／docs stage 2 章節改指向 hippo（R-18 同 PR）；R-22 懸空引用清理
- [ ] 4.8 主 repo 全測試綠（unit + integration，integration_test_gate）

## 5. 驗收與收尾

- [ ] 5.1 雙 repo CI 全綠；CI 驗證從 pinned SHA 可重現安裝
- [ ] 5.2 既有主機實機 cutover 驗證：dream 服務由 hippo 接手、`~/.agents/memory` 零遷移、doctor 全綠
- [ ] 5.3 secret 遷移指引發布（`~/.config/paulsha-hippo/secret.env`）；回滾程序文件化（還原 start.sh 段 + revert PR + pip 移除）
- [ ] 5.4 #125 Phase 1 DoD 勾稽與 issue 更新；本 change 進 archive
