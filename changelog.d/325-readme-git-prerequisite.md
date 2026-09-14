---
type: fix
scope: docs
issue: 325
---
README §A end-user 安裝補上系統前置段，明列 `python3`、`python3-venv`、`git`（Ubuntu／Debian 給 `sudo apt install` 一行）並說明 git 是因為 wheel 的 hippo／cortex 依賴為 `git+https://…@<SHA>` direct reference、pip 解析時必須呼叫系統 git；step 5「確認」補排解（`pip install` 非零就停、`ls venv/bin/paulshaclaw`、stderr 含 `Cannot find command 'git'` 即缺 git）；pipx 段補 pipx 本身怎麼裝、`pipx ensurepath` 後要開新 shell、同樣需要 git。`docs/release-contract.md` §5.1 補「end-user 系統前置含 git」條款。此為 2026-08-26 Docker 四容器重現（ubuntu 24.04／22.04、Python 3.12／3.10）證實的安裝故障：無 git 的機器照 README 字面安裝 v0.2.7 會在 step 4 exit 1、`paulshaclaw` 指令不存在。
