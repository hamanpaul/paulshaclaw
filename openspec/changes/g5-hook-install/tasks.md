## 1. 清單集中與冪等

- [ ] 1.1 RED：假 $HOME 二次執行冪等測試（檔案零變更、settings 無重複）
- [ ] 1.2 hooks 複製清單集中宣告＋reconcile 冪等；GREEN

## 2. --verify

- [ ] 2.1 RED：四檢測試（壞語法/缺註冊/缺 env 檔/stale hash 各一 fixture→非零指名；完好→0）
- [ ] 2.2 install.sh --verify 實作（py_compile/bash -n、註冊檢查、env 存在性不印值、sha256 stale 清單）；GREEN

## 3. abspath 一致性

- [ ] 3.1 RED：lint 測試（植入 /home/ 字面 fixture hook→抓到）
- [ ] 3.2 既有 hooks 路徑統一（shell→${PSC_REPO_ROOT}；Python→config.paths facade）＋verify 內建 lint；GREEN
- [ ] 3.3 重部署（install --skip-venv）＋import 健檢（複製坑收尾）

## 4. 收尾

- [ ] 4.1 乾淨環境（假 $HOME）e2e：install→verify 綠
- [ ] 4.2 全套件綠；PR body `Closes #128`
