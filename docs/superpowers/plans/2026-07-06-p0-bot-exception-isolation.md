# P0 Bot Listener 例外隔離 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **實作者：gpt5.3-codex**。repo `~/prj_pri/paulshaclaw`，開 `feature/196-bot-exception-isolation` worktree；不得在 main 工作。測試跑 `python3 -m pytest tests/ -q`（系統 python 有 pytest；`.venv` 只給 cockpit UI 測試用）。

**Goal:** handler 例外不再殺死 Telegram listener；bot 進程死亡由 start.sh 自動重生（#196）。

**Architecture:** 最外圈保險絲（broad except 包 `router.handle_message` 呼叫點）＋ start.sh bot supervisor（backoff respawn）。錨點：`paulshaclaw/bot/listener.py:313` 的 `result = self.router.handle_message(...)`；respawn 沿 `scripts/start.sh` 既有 loop 函式慣例（`start_dream_loop` 等，見 start.sh:191 起）。

**Tech Stack:** Python 3.10+、bash（start.sh）、pytest。

**依據**：`openspec/changes/p0-bot-exception-isolation/`＋`docs/superpowers/specs/2026-07-06-p0-bot-exception-isolation-design.md`。

---

### Task 1: handler 例外隔離

**Files:**
- Modify: `paulshaclaw/bot/listener.py:308-315`（`handle_message` 呼叫點外圈）
- Test: `tests/test_telegram_listener.py`（新增測試，檔案既有）

- [ ] **Step 1: 寫失敗測試**

```python
def test_handler_exception_does_not_kill_listener(monkeypatch):
    listener, client = _build_listener_with_fake_client()   # 沿本檔既有 fixture 慣例
    def boom(*, user_id, text):
        raise ValueError("simulated handler crash")
    monkeypatch.setattr(listener.router, "handle_message", boom)
    listener._handle_message(_make_text_update("/tmate"))    # 呼叫既有訊息處理入口（名稱以檔內為準，錨點 listener.py:291-315）
    # listener 未拋例外＝loop 存活；且回覆了單行錯誤
    assert any("指令執行失敗" in m and "ValueError" in m for m in client.sent_texts)
    assert all("Traceback" not in m for m in client.sent_texts)

def test_keyboard_interrupt_propagates(monkeypatch):
    listener, _ = _build_listener_with_fake_client()
    def stop(*, user_id, text):
        raise KeyboardInterrupt
    monkeypatch.setattr(listener.router, "handle_message", stop)
    with pytest.raises(KeyboardInterrupt):
        listener._handle_message(_make_text_update("/x"))
```

- [ ] **Step 2: 跑它 fail**

Run: `python3 -m pytest tests/test_telegram_listener.py -k handler_exception -v`
Expected: FAIL——`ValueError` 直接冒出（現行無外圈攔截）。

- [ ] **Step 3: 最小實作**（listener.py:313 附近）

```python
        logger.info("IN  user=%d chat=%d text=%r", user_id, chat_id, text)
        try:
            result = self.router.handle_message(user_id=user_id, text=text)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:  # noqa: BLE001 — 最外圈保險絲（#196）：單一指令失敗域=該指令
            logger.exception("HANDLER_ERROR user=%d chat=%d text=%r", user_id, chat_id, text)
            self._safe_send(chat_id=chat_id, text=f"指令執行失敗：{type(error).__name__}")
            return
        reply = str(result["message"])
        self._safe_send(chat_id=chat_id, text=reply)
```

- [ ] **Step 4: GREEN＋零回歸**

Run: `python3 -m pytest tests/test_telegram_listener.py -q`
Expected: 全 PASS（含既有 fail-closed dispatch 守門測試）。

- [ ] **Step 5: Commit** — `fix(bot): handler 例外隔離——broad except 保險絲，listener 不再因單一指令死亡（#196）`

### Task 2: start.sh bot respawn（backoff）

**Files:**
- Modify: `scripts/start.sh`（bot 啟動段改 supervisor 函式；沿 `start_dream_loop` 函式風格，錨點 start.sh:191）
- Test: `tests/test_start_sh.py` 或新檔 `tests/test_start_sh_bot_respawn.py`

- [ ] **Step 1: 寫失敗測試**（stub 方式，**避免 SIGKILL 情境**——#195 既知坑）

```python
def test_bot_respawn_backoff(tmp_path):
    # 以 bash 函式單測：source start.sh 的 respawn 函式，bot 命令用「失敗2次後建立 sentinel 並常駐」的 stub
    stub = tmp_path / "bot_stub.sh"
    stub.write_text("#!/bin/bash\nn=$(cat n 2>/dev/null || echo 0)\necho $((n+1)) > n\n[ \"$n\" -ge 2 ] && { touch ok; exec sleep 60; }\nexit 1\n")
    stub.chmod(0o755)
    out = subprocess.run(
        ["bash", "-c", f"source scripts/start.sh --source-only; PSC_BOT_BACKOFF_BASE=0 start_bot_supervised {stub} & sleep 1; ls {tmp_path}"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=30,
    )
    assert "ok" in out.stdout   # 兩次失敗後第三次成功＝backoff 重拉有效
```

- [ ] **Step 2: RED**（`start_bot_supervised` 不存在／`--source-only` 未支援 → fail）
- [ ] **Step 3: 實作**：start.sh 新增

```bash
# #196：bot supervisor——poll loop 本體意外退出時 backoff 重拉；只管 bot，不動其他 loop。
start_bot_supervised() {
  local cmd="$1" delay="${PSC_BOT_BACKOFF_BASE:-5}" count=0
  (
    while true; do
      "$cmd" && break            # 正常結束（cleanup 收尾）不重拉
      count=$((count + 1))
      echo "bot exited unexpectedly; respawn #$count in ${delay}s" >&2
      sleep "$delay"
      delay=$(( delay >= 120 ? 120 : delay * 6 ))   # 5→30→120 cap（BASE=5 時）
    done
  ) &
}
```

  並：既有 bot 啟動行改經 `start_bot_supervised`；頂部支援 `--source-only`（`[[ "${1:-}" == "--source-only" ]] && return 0 2>/dev/null`）供測試 source；cleanup() 收 supervisor 子行程。
- [ ] **Step 4: GREEN**：`python3 -m pytest tests/test_start_sh_bot_respawn.py -v`＋既有 start.sh 測試零回歸。
- [ ] **Step 5: 手動驗證**（可選、on-host）：`kill <bot pid>` → log 見 `respawn #1 in 5s`、bot 回來、dream/cost/manager loop 不受影響。
- [ ] **Step 6: Commit** — `fix(start): bot supervisor backoff respawn（#196）`；PR body `Closes #196`。

---

**Self-review**：spec 2 requirement ↔ Task 1（隔離＋窄型別語意不變由零回歸保證）、Task 2（respawn）；KeyboardInterrupt/SystemExit 放行已入測試；無 TBD。
