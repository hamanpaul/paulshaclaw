# Cockpit Wrapped-Minicom Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cockpit WORK 面板把「經 `serialwrap-minicom` wrapper 啟動、tmux 回報 command 為 shell」的 minicom pane 標成 `minicom COMx`，而非退回 cwd basename。

**Architecture:** 只改 `derive_summary`——在既有 `command == "minicom"` 分支之後、`pane_current_path` 分支之前，對「title 不可用且 command ∈ shell 集合」的 pane 插入一次 tty-based `_minicom_summary` 探測（`ps -t` 掃該 tty 找 minicom argv，能穿透 wrapper）；命中才覆蓋、未命中透明退回既有 cwd fallback。偵測函式 `_minicom_summary` 不動（已驗證能穿透 wrapper）。

**Tech Stack:** Python 3.12、stdlib `subprocess`/`re`/`pathlib`、unittest（`~/.local/bin/pytest` 執行）、openspec。

## Global Constraints

- 只動 `paulshaclaw/cockpit/tmux.py`（僅 `derive_summary` 與一個 module 級 shell 常數）與 `tests/test_stage11_operator_cockpit.py`。
- 直跑 minicom（`command == "minicom"`）分支與所有非 shell/非 minicom pane 行為零變化。
- `_minicom_summary` 的偵測語意不改（含 1s timeout、取第一個命中）。
- 成本邊界：只對「無 title 的 shell pane」多跑一次 `ps`；empty `pane_tty` 時 `_minicom_summary` 立即回 None、不觸發 subprocess。
- language zh-TW（本 repo 屬 hamanpaul）；commit 走 conventional，`Co-Authored-By` trailer 對齊使用中的 agent。
- 未經使用者明確要求，不 push / 不開 PR（local commit 收尾）。

---

### Task 1: derive_summary 探測 wrapper 底下的 minicom

**Files:**
- Modify: `paulshaclaw/cockpit/tmux.py`（`derive_summary`，約 107-117 行；新增 module 級常數 `_SHELL_COMMANDS`）
- Test: `tests/test_stage11_operator_cockpit.py`（`Stage11StateTests` 內，緊接既有 `test_derive_summary_*` 群）

**Interfaces:**
- Consumes: 既有 `_minicom_summary(tty: str) -> str | None`（`paulshaclaw/cockpit/tmux.py`，未改）；`PaneRecord`（欄位 `title`/`command`/`pane_tty`/`pane_current_path`/`host_short`）；測試 helper `pane_record(pane_id, *, title, command, pane_tty, pane_current_path, host_short, ...)`。
- Produces: `derive_summary(pane: PaneRecord) -> str`（簽名不變；新增「wrapper 底下 minicom → `minicom COMx`」行為）；module 常數 `_SHELL_COMMANDS: frozenset[str]`。

- [ ] **Step 1: 寫失敗測試（wrapped minicom）**

在 `tests/test_stage11_operator_cockpit.py` 既有 `test_derive_summary_hostname_title_falls_back_to_cwd_name` 之後新增：

```python
    def test_derive_summary_wrapped_minicom_reads_com_from_tty(self) -> None:
        # serialwrap-minicom wrapper 底下：tmux 回報 command=bash，但 tty 上跑著 minicom。
        pane = pane_record(
            "%3",
            title="",
            command="bash",
            pane_tty="/dev/pts/9",
            pane_current_path="/home/paul_chen",
            host_short="9900X",
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=(
                "  bash /home/paul_chen/.local/bin/serialwrap-minicom COM0\n"
                "  /usr/bin/minicom -D /dev/pts/8 --color=on -C /home/paul_chen/b-log/mini_COM0_x.log\n"
            ),
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "minicom COM0")
```

- [ ] **Step 2: 跑測試確認 RED（正確原因）**

Run: `~/.local/bin/pytest tests/test_stage11_operator_cockpit.py -k wrapped_minicom -q`
Expected: FAIL，實際值為 `paul_chen`（cwd basename），非 `minicom COM0` —— 證明 `command == "minicom"` guard 擋住了偵測。

- [ ] **Step 3: 寫失敗測試（shell pane 無 minicom → 透明退回 cwd）**

再新增（緊接上一個測試）：

```python
    def test_derive_summary_shell_pane_without_minicom_falls_back_to_cwd(self) -> None:
        # 一般 idle bash pane：tty 上沒有 minicom，須退回 cwd basename、不誤標 minicom。
        pane = pane_record(
            "%1",
            title="",
            command="bash",
            pane_tty="/dev/pts/3",
            pane_current_path="/home/paul/prj/repo-a",
            host_short="9900X",
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="  -bash\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed):
            self.assertEqual(derive_summary(pane), "repo-a")
```

- [ ] **Step 4: 跑兩個新測試確認狀態**

Run: `~/.local/bin/pytest tests/test_stage11_operator_cockpit.py -k "wrapped_minicom or shell_pane_without_minicom" -q`
Expected: `wrapped_minicom` FAIL（回 `paul_chen`）；`shell_pane_without_minicom` PASS（改動前 command=bash 非 minicom、有 cwd → 已回 `repo-a`；此案守住「別回歸成誤標」）。

- [ ] **Step 5: 實作最小修改**

在 `paulshaclaw/cockpit/tmux.py`，於 `_MINICOM_DEVICE_RE = ...` 之後新增常數：

```python
# minicom 常經 wrapper（如 serialwrap-minicom，bash script）啟動，此時 tmux
# #{pane_current_command} 回報的是 shell 而非 minicom。這組 shell 名用來判斷
# 「值得對該 pane 的 tty 探一次 minicom」，把成本鎖在真正可能藏 minicom 的 pane。
_SHELL_COMMANDS = frozenset({"bash", "sh", "zsh", "dash", "ash", "fish"})
```

把 `derive_summary` 改為（在 minicom 分支後、cwd 分支前插入 shell 探測）：

```python
def derive_summary(pane: PaneRecord) -> str:
    """A readable work-list label: the title when set, else a command fallback."""
    title = pane.title.strip()
    host_short = pane.host_short.strip()
    if title and title != host_short:
        return title
    if pane.command == "minicom":
        return _minicom_summary(pane.pane_tty) or "minicom"
    # minicom 常經 wrapper（serialwrap-minicom）啟動，tmux 只看得到外層 shell；
    # 對 shell pane 探一次 tty，讓 wrapper 底下的 minicom 仍以 COM 埠命名。
    # _minicom_summary 對空 tty 立即回 None，故無 tty 的 shell pane 不觸發 ps。
    if pane.command in _SHELL_COMMANDS:
        wrapped = _minicom_summary(pane.pane_tty)
        if wrapped:
            return wrapped
    if pane.pane_current_path:
        return Path(pane.pane_current_path).name or "/"
    return f"[{pane.command}]" if pane.command else ""
```

- [ ] **Step 6: 跑新測試轉綠**

Run: `~/.local/bin/pytest tests/test_stage11_operator_cockpit.py -k "wrapped_minicom or shell_pane_without_minicom" -q`
Expected: 兩個都 PASS。

- [ ] **Step 7: 全 stage11 + cockpit 套件回歸**

Run: `~/.local/bin/pytest tests/test_stage11_operator_cockpit.py tests/test_cockpit_redesign.py tests/test_cockpit_sysmon.py tests/test_cockpit_cost_bar.py tests/test_cockpit_branding.py -q`
Expected: 全 PASS。特別確認既有 `test_derive_summary_minicom_reads_com_from_process`（直跑 minicom 回歸）、`test_derive_summary_hostname_title_falls_back_to_cwd_name`、`test_derive_summary_root_path_falls_back_to_slash`（command=bash、pane_tty="" → `_minicom_summary` 回 None）皆仍綠。

- [ ] **Step 8: live 佐證（fail-soft，非 gate）**

Run: `.venv/bin/python -c "from paulshaclaw.cockpit.tmux import TmuxClient, derive_summary; tc=TmuxClient(); [print(p.pane_id, derive_summary(p)) for p in tc.list_panes(cockpit_pane_id='%0', capture_previews=False) if p.pane_id in ('%3','%4')]"`
Expected: `%3 minicom COM0` / `%4 minicom COM1`（依現場 tty；若現場已無 minicom 則顯示 cwd，屬正常）。

- [ ] **Step 9: Commit**

```bash
git add paulshaclaw/cockpit/tmux.py tests/test_stage11_operator_cockpit.py
git commit -m "$(cat <<'EOF'
fix(cockpit): WORK 清單辨識 wrapper 底下的 minicom（tty 探測）

serialwrap-minicom wrapper 啟動的 minicom 讓 tmux 回報 command=bash，
derive_summary 的 command==minicom guard 失效、落到 cwd basename。改在
shell pane 上先試 tty-based _minicom_summary，命中才標 minicom COMx。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

（注意：archive / policy gate / 最終 commit 收尾在 apply 階段的收尾任務處理；此處 commit 為實作交付點。）

## Self-Review

**1. Spec coverage** — spec delta 三個 scenario 對映：
- 「Wrapped minicom pane is labeled by its COM port」→ Task1 Step1 測試 + Step5 shell 探測。
- 「Non-minicom shell pane still falls back to current path」→ Task1 Step3 測試 + Step5 「命中才覆蓋」。
- 「Directly launched minicom keeps existing detection」→ 既有 `test_derive_summary_minicom_reads_com_from_process` 守（Step7 明列回歸；不重複新增，DRY）。

**2. Placeholder scan** — 無 TBD/TODO；所有 step 附實際 code 與命令。

**3. Type consistency** — `_minicom_summary(tty: str) -> str | None`、`derive_summary(pane) -> str`、`_SHELL_COMMANDS: frozenset[str]` 全一致；測試 helper `pane_record(...)` 參數與既有用法一致。
