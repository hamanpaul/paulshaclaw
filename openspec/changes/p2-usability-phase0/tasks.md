## 1. PR-A：psc 入口＋版號＋清殼（無依賴，可先行）

- [ ] 1.1 RED：`psc memory dream --help` 等路由測試（entry 不存在先 fail）
- [ ] 1.2 新增 `paulshaclaw/cli.py` 薄 dispatcher＋`[project.scripts] psc`（透傳 argv、未知子命令 usage+exit 2）
- [ ] 1.3 VERSION → `0.1.0` 對齊 pyproject＋版號一致性 pytest（正規化 semver、tag 去 `v` 前綴比對）
- [ ] 1.4 移除 `paulshaclaw/janitor/`、`paulshaclaw/chat/` 空殼（保留 `config/`）
- [ ] 1.5 GREEN＋`pip install -e .` 實測 `psc memory dream status`；tag `v0.1.0` 由 owner 打或授權代行

## 2. PR-B：env facade＋LLM 讀點收斂（依賴 P0-1 Stage A env 化先落）

- [ ] 2.1 RED：facade 單元測試（`PSC_*` 覆寫／未設走契約預設／假 `$HOME` 隔離）
- [ ] 2.2 新增 `paulshaclaw/config/paths.py`（僅 stdlib、禁 import 業務包）
- [ ] 2.3 遷移 29 處 `Path.home()` 呼叫點＋`coordinator/seams.py`、`memory/importer/backfill.py` 硬編碼預設，收編 `PSC_EXTRA_CORPUS_ROOT`（別名保留一版）
- [ ] 2.4 LLM 後端讀點集中經 facade/config＋替換後端文件（config 鍵、env 覆寫鏈）
- [ ] 2.5 GREEN：非 tests 直接 `Path.home()` 呼叫點僅剩 facade 本體；假 `$HOME` 全套件綠
- [ ] 2.6 hooks 若引用 facade：重跑 install 同步並 import 健檢（複製部署坑）

## 3. 收尾

- [ ] 3.1 兩 PR 各自全套件綠；PR body 引用 `Closes #91`（PR-B）
