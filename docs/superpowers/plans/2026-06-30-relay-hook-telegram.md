# #120 relay/hook → Telegram 統一接線 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 manager 自主派工進度與 codex/copilot 互動 pane 的本輪回覆都接到 Telegram，共用 `reply_bridge.py`。

**Architecture:** 兩條 producer 各自以 marker gate（manager=`PSC_SLICE_ID`、互動=本輪 `[bro:id]`）收斂到 `reply_bridge.py → Telegram`。Half 1 改 `psc-relay-hook.sh`；Half 2 新增 `psc-bro-return.py`（turn-scoped 自我發現，複用 importer transcript readers），裝進 codex `Stop`/copilot `agentStop`。

**Tech Stack:** bash、Python 3（stdlib + `paulshaclaw.memory.importer.adapters.base`）、unittest/pytest、reply_bridge.py（stdlib-only）。

參考：`docs/superpowers/specs/2026-06-30-120-relay-hook-telegram-wiring-design.md`、`openspec/changes/relay-hook-telegram/`。

---

## File Structure

- Modify `scripts/coordinator/psc-relay-hook.sh` — Half 1：寫檔後 gate 於 `PSC_SLICE_ID` 推 Telegram。新增可覆寫的 `PSC_REPLY_BRIDGE` 供測試注入。
- Create `scripts/gemma4-hooks/psc-bro-return.py` — Half 2：turn-scoped 回程 hook（`--platform codex|copilot`）。
- Modify `tests/test_coordinator_relay_hook.py` — Half 1 RED + 既有測試中和真 bridge。
- Create `tests/test_psc_bro_return.py` — Half 2 RED。
- Modify codex/copilot hook 模板與 install 腳本 — 安裝接線（Task 4）。

---

### Task 1: Half 1 — psc-relay-hook.sh 推 Telegram（gate 於 PSC_SLICE_ID）

**Files:**
- Modify: `tests/test_coordinator_relay_hook.py`
- Modify: `scripts/coordinator/psc-relay-hook.sh`

- [ ] **Step 1: 中和既有測試對真 bridge 的觸碰 + 寫 RED 新測試**

把 `tests/test_coordinator_relay_hook.py` 改為（既有兩例補 `PSC_REPLY_BRIDGE` 指向不存在路徑以跳過真 bridge；新增三例）：

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = "scripts/coordinator/psc-relay-hook.sh"

# 注入用：把 reply_bridge 換成記錄 argv 的 stub（避免碰真 Telegram）。
_STUB = (
    "#!/usr/bin/env python3\n"
    "import sys, os\n"
    "open(os.environ['BRIDGE_LOG'], 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n"
)


def _write_stub(p: Path) -> None:
    p.write_text(_STUB, encoding="utf-8")
    p.chmod(0o755)


class RelayHookTests(unittest.TestCase):
    def test_emits_slice_tagged_payload(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "relay.out"
            env = {**os.environ, "PSC_SLICE_ID": "slice-a",
                   "PSC_RELAY_TARGET": str(out), "PSC_RELAY_EVENT": "stop",
                   "PSC_REPLY_BRIDGE": str(Path(d) / "nope.py")}  # 不存在 → 跳過 bridge
            subprocess.run(["bash", HOOK], env=env, check=True)
            text = out.read_text(encoding="utf-8")
            self.assertIn("slice-a", text)
            self.assertIn("stop", text)

    def test_missing_target_does_not_fail(self) -> None:
        env = {**os.environ, "PSC_SLICE_ID": "slice-a", "PSC_RELAY_EVENT": "stop",
               "PSC_REPLY_BRIDGE": "/nonexistent/reply_bridge.py"}
        env.pop("PSC_RELAY_TARGET", None)
        r = subprocess.run(["bash", HOOK], env=env)
        self.assertEqual(r.returncode, 0)

    def test_slice_set_pushes_telegram(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "bridge.py"
            _write_stub(stub)
            log = Path(d) / "bridge.log"
            env = {**os.environ, "PSC_SLICE_ID": "slice-a", "PSC_RELAY_EVENT": "stop",
                   "PSC_RELAY_TARGET": str(Path(d) / "relay.out"),
                   "PSC_REPLY_BRIDGE": str(stub), "BRIDGE_LOG": str(log)}
            subprocess.run(["bash", HOOK], env=env, check=True)
            argv = log.read_text(encoding="utf-8")
            self.assertIn("--text", argv)
            self.assertIn("slice-a", argv)
            self.assertNotIn("--source-user-id", argv)  # broadcast

    def test_no_slice_does_not_push(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "bridge.py"
            _write_stub(stub)
            log = Path(d) / "bridge.log"
            env = {**os.environ, "PSC_RELAY_EVENT": "stop",
                   "PSC_RELAY_TARGET": str(Path(d) / "relay.out"),
                   "PSC_REPLY_BRIDGE": str(stub), "BRIDGE_LOG": str(log)}
            env.pop("PSC_SLICE_ID", None)
            subprocess.run(["bash", HOOK], env=env, check=True)
            self.assertFalse(log.exists(), "互動 session（無 slice）不應推 Telegram")

    def test_unknown_slice_does_not_push(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "bridge.py"
            _write_stub(stub)
            log = Path(d) / "bridge.log"
            env = {**os.environ, "PSC_SLICE_ID": "unknown", "PSC_RELAY_EVENT": "stop",
                   "PSC_RELAY_TARGET": str(Path(d) / "relay.out"),
                   "PSC_REPLY_BRIDGE": str(stub), "BRIDGE_LOG": str(log)}
            subprocess.run(["bash", HOOK], env=env, check=True)
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `PYTHONPATH=. ~/.local/bin/pytest tests/test_coordinator_relay_hook.py -v`
Expected: `test_slice_set_pushes_telegram` FAIL（hook 還沒呼叫 bridge，log 不存在）；其餘 PASS。

- [ ] **Step 3: 改 psc-relay-hook.sh（GREEN）**

把 `scripts/coordinator/psc-relay-hook.sh` 改為：

```sh
#!/usr/bin/env bash
# Shared session_start/stop relay hook. Best-effort only: relay failures must not
# affect agent execution or completion detection.
set -u

slice="${PSC_SLICE_ID:-unknown}"
event="${PSC_RELAY_EVENT:-unknown}"
target="${PSC_RELAY_TARGET:-}"
msg="[manager] slice=${slice} event=${event}"

if [[ -n "$target" ]]; then
  printf '%s\n' "$msg" >>"$target" 2>/dev/null || true
fi

# #120 Half 1: 僅 manager 派工（launcher 注入 PSC_SLICE_ID）才推 Telegram；
# 互動 session 無 slice → no-op，避免灌爆。broadcast（不帶 --source-user-id）。
reply_bridge="${PSC_REPLY_BRIDGE:-$HOME/.agents/skills/bro/scripts/reply_bridge.py}"
if [[ -n "${PSC_SLICE_ID:-}" && "${PSC_SLICE_ID}" != "unknown" && -f "$reply_bridge" ]]; then
  python3 "$reply_bridge" --text "$msg" >/dev/null 2>&1 || true
fi

exit 0
```

- [ ] **Step 4: 跑測試確認 GREEN + 語法**

Run: `bash -n scripts/coordinator/psc-relay-hook.sh && PYTHONPATH=. ~/.local/bin/pytest tests/test_coordinator_relay_hook.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/coordinator/psc-relay-hook.sh tests/test_coordinator_relay_hook.py
git commit -m "feat(coordinator): #120 Half1 relay hook gate於PSC_SLICE_ID推Telegram"
```

---

### Task 2: Half 2 — psc-bro-return.py（turn-scoped 回程）

**Files:**
- Create: `tests/test_psc_bro_return.py`
- Create: `scripts/gemma4-hooks/psc-bro-return.py`

- [ ] **Step 1: 寫 RED 測試**

`tests/test_psc_bro_return.py`（import 模組、注入 fake sender + monkeypatch readers）：

```python
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "psc_bro_return", REPO / "scripts" / "gemma4-hooks" / "psc-bro-return.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class _Sender:
    def __init__(self):
        self.calls = []

    def __call__(self, user_id, text):
        self.calls.append((user_id, text))


class TurnScopedBindingTests(unittest.TestCase):
    def _run(self, platform, prompts, reply):
        snd = _Sender()
        # readers 注入：直接打 handle，繞過真 transcript
        sent = mod.handle_resolved(prompts=prompts, reply=reply, sender=snd)
        return snd, sent

    def test_first_bro_then_local_no_send(self):
        snd, sent = self._run("codex", ["[bro:111] a", "local b"], "r")
        self.assertFalse(sent)
        self.assertEqual(snd.calls, [])

    def test_first_bro_then_different_user_sends_new(self):
        snd, sent = self._run("codex", ["[bro:111] a", "[bro:222] b"], "r")
        self.assertTrue(sent)
        self.assertEqual(snd.calls, [(222, "r")])

    def test_first_local_then_bro_sends_bro(self):
        snd, sent = self._run("codex", ["local a", "[bro:111] b"], "r")
        self.assertEqual(snd.calls, [(111, "r")])

    def test_no_marker_no_send(self):
        snd, sent = self._run("codex", ["local only"], "r")
        self.assertEqual(snd.calls, [])

    def test_reply_unreadable_skips_no_empty_notice(self):
        # reply=None 代表讀不到 → skip，不送 EMPTY_NOTICE
        snd, sent = self._run("codex", ["[bro:111] a"], None)
        self.assertFalse(sent)
        self.assertEqual(snd.calls, [])

    def test_reply_empty_sends_empty_notice(self):
        snd, sent = self._run("codex", ["[bro:111] a"], "")
        self.assertEqual(snd.calls, [(111, mod.EMPTY_NOTICE)])


class PlatformResolveTests(unittest.TestCase):
    def test_copilot_uses_history(self):
        # monkeypatch read_copilot_history → 回 prompts + assistant
        orig = mod.read_copilot_history
        mod.read_copilot_history = lambda root, sid: {
            "user_prompts": ["[bro:7] hi"], "assistant_summary": "yo"}
        try:
            prompts, reply = mod.resolve("copilot", {"session_id": "s1"})
        finally:
            mod.read_copilot_history = orig
        self.assertEqual(prompts[-1], "[bro:7] hi")
        self.assertEqual(reply, "yo")

    def test_codex_reply_from_payload_missing_key_is_none(self):
        orig = mod.read_codex_rollout
        mod.read_codex_rollout = lambda p: {"user_prompts": ["[bro:7] hi"]}
        try:
            # 無 last_assistant_message key → reply=None（unreadable）
            prompts, reply = mod.resolve("codex", {"transcript_path": "/x"})
        finally:
            mod.read_codex_rollout = orig
        self.assertEqual(prompts[-1], "[bro:7] hi")
        self.assertIsNone(reply)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `PYTHONPATH=. ~/.local/bin/pytest tests/test_psc_bro_return.py -v`
Expected: FAIL（檔案/函式不存在：`ModuleNotFoundError`/`AttributeError`）。

- [ ] **Step 3: 寫 psc-bro-return.py（GREEN）**

`scripts/gemma4-hooks/psc-bro-return.py`：

```python
#!/usr/bin/env python3
"""codex Stop / copilot agentStop hook: 把本輪回覆送回 bro Telegram user（turn-scoped）。

turn-scoped：用本輪 user_prompts[-1] 的 [bro:<id>] 自我發現收件 user（無 marker → no-op）。
reply：copilot 取自 read_copilot_history、codex 取自 Stop event payload last_assistant_message。
reply 為 None（讀不到）→ skip 不送；為 "" → 送 EMPTY_NOTICE；hook MUST always exit 0。
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from paulshaclaw.memory.importer.adapters.base import (
    read_codex_rollout,
    read_copilot_history,
)

BRO_RE = re.compile(r"^\s*\[bro:(\d+)\]")
REPLY_BRIDGE = Path.home() / ".agents" / "skills" / "bro" / "scripts" / "reply_bridge.py"
LOG = Path.home() / ".agents" / "log" / "bro-hook.log"
EMPTY_NOTICE = "（已完成，無文字輸出）"


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} psc-bro-return {stage}: {exc!r}\n")
    except Exception:
        pass


def _send_via_bridge(user_id: int, text: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPLY_BRIDGE), "--source-user-id", str(user_id), "--text", text],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False,
    )
    if result.returncode != 0:
        _log("send", RuntimeError(f"reply_bridge exit {result.returncode}: {(result.stderr or '').strip()[:500]}"))


def _discover_user_id(prompts: list[str]) -> int | None:
    """turn-scoped：本輪 = 最後一則 user prompt。無 marker → None。"""
    if not prompts:
        return None
    m = BRO_RE.match(prompts[-1] or "")
    return int(m.group(1)) if m else None


def resolve(platform: str, event: dict) -> tuple[list[str], str | None]:
    """回 (user_prompts, reply)。reply=None 代表讀不到（skip）、"" 代表真無輸出。"""
    if platform == "copilot":
        data = read_copilot_history(Path.home(), str(event.get("session_id") or ""))
        prompts = data.get("user_prompts", []) or []
        # history 讀到（prompts 非空）→ assistant_summary 即真相；讀不到 → prompts 空 → 後續 no-op
        reply = data.get("assistant_summary", "") if prompts else None
        return prompts, reply
    # codex
    tp = event.get("transcript_path")
    prompts: list[str] = []
    if tp:
        try:
            prompts = read_codex_rollout(tp).get("user_prompts", []) or []
        except Exception as exc:
            _log("rollout", exc)
    # reply 來自 event payload；缺 key → None（unreadable）；present(含 "") → 用
    reply = event["last_assistant_message"] if "last_assistant_message" in event else None
    if reply is not None and not isinstance(reply, str):
        reply = None
    return prompts, reply


def handle_resolved(*, prompts: list[str], reply: str | None, sender=_send_via_bridge) -> bool:
    user_id = _discover_user_id(prompts)
    if user_id is None:
        return False  # turn-scoped no-op（本地輸入 / 非 bro 路由 / manager headless）
    if reply is None:
        _log("reply", RuntimeError("本輪回覆讀不到 → skip（不送 EMPTY_NOTICE）"))
        return False
    try:
        sender(user_id, reply or EMPTY_NOTICE)
    except Exception as exc:
        _log("send", exc)
    return True


def handle(event: dict, platform: str, sender=_send_via_bridge) -> bool:
    try:
        prompts, reply = resolve(platform, event)
    except Exception as exc:
        _log("resolve", exc)
        return False
    return handle_resolved(prompts=prompts, reply=reply, sender=sender)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["codex", "copilot"])
    args = parser.parse_args()
    try:
        handle(json.load(sys.stdin), args.platform)
    except Exception as exc:  # hook must never break the agent
        _log("main", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑測試確認 GREEN**

Run: `PYTHONPATH=. ~/.local/bin/pytest tests/test_psc_bro_return.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/gemma4-hooks/psc-bro-return.py tests/test_psc_bro_return.py
git commit -m "feat(bro): #120 Half2 codex/copilot turn-scoped 回程 hook"
```

---

### Task 3: 安裝接線（codex Stop / copilot agentStop）

**Files:**
- Modify/Create: codex/copilot hook 模板（依現有 `scripts/coordinator/hooks/` 慣例放回程 entry，或 install 腳本內嵌）
- Modify: 對應 install 腳本（找出裝 relay hook 的同一支）
- Test: install merge 若有 Python 可測點則加測試

- [ ] **Step 1: 找出既有 relay hook 的安裝點**

Run: `grep -rn "managedBy.*psc-coordinator-relay\|hooks/codex.json\|~/.codex/hooks.json\|agentStop" scripts/ paulshaclaw/ install.sh 2>/dev/null`
確認三家 hook config 的安裝/merge 邏輯位置（relay hook 既已裝在 `~/.codex/hooks.json`，沿用同一 merge 路徑）。

- [ ] **Step 2: 加 `psc-bro-return` entry（managedBy 標記，nested merge 保留既有）**

於 codex `Stop` / copilot `agentStop` 加一條：
```
codex Stop  ：command = "<memory-venv-python> <repo>/scripts/gemma4-hooks/psc-bro-return.py --platform codex"
copilot agentStop：bash = "<memory-venv-python> <repo>/scripts/gemma4-hooks/psc-bro-return.py --platform copilot"
managedBy: psc-bro-return
```
venv 用與 `codex_session_end.py` 同源的 `~/.agents/memory/hooks/.venv/bin/python`（package-aware）。merge MUST 保留 `psc-coordinator-relay` / `paulsha-memory` 既有 entry。

- [ ] **Step 3: 若 merge 邏輯在 Python → 加單元測試（保留既有 entry + 冪等重裝）；若純 shell → 加 install dry-run 驗證 entry 存在且既有未失。**

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(bro): #120 安裝 codex/copilot 回程 hook（nested merge 保留既有）"
```

---

### Task 4: Verify / docs / openspec 收尾

- [ ] **Step 1: 跑相關測試全綠**

Run: `PYTHONPATH=. ~/.local/bin/pytest tests/test_coordinator_relay_hook.py tests/test_psc_bro_return.py tests/test_gemma4_bro_hooks.py tests/test_telegram_reply.py -q`
Expected: 全 PASS（既有不回歸）。

- [ ] **Step 2: docs 對齊（R-18）**

`README.md` / 相關 docs 補：manager 進度與 codex/copilot 回覆已接 Telegram；capture-pane fallback / 節流為 follow-up。

- [ ] **Step 3: openspec archive + policy gate + commit（phase 9–10，本地）**

```bash
openspec archive relay-hook-telegram
python3 -m policy_check --repo . 2>/dev/null || true   # 若有
PYTHONPATH=. ~/.local/bin/pytest -q
git add -A && git commit -m "docs(openspec): archive relay-hook-telegram (#120)"
```

---

## Self-Review

**Spec coverage：**
- coordinator-headless-dispatch MODIFIED（推 Telegram / 互動不 spam / 失敗不影響）→ Task 1（含 `test_slice_set_pushes_telegram`、`test_no_slice_does_not_push`、`test_unknown_slice_does_not_push`、`test_missing_target_does_not_fail`）。✓
- agent-conversation-routing ADDED（turn-scoped 四案 + skip-unreadable + empty→notice）→ Task 2 全測試對應。✓
- 安裝接線（nested merge 保留既有）→ Task 3。✓
- 非目標（去程 / Claude bro / capture-pane / 節流）：未列任務，正確。✓

**Placeholder scan：** Task 3 的安裝點需實作時 grep 定位（既有 hook 安裝邏輯尚未在本 plan 逐行展開，因其位置依 grep 結果而定）——此為唯一需現場確認處，已在 Step 1 明示指令。其餘均含完整 code。

**Type consistency：** `handle_resolved(prompts, reply, sender)` / `resolve(platform, event)` / `_discover_user_id(prompts)` / `EMPTY_NOTICE` 在測試與實作一致；reply 語意 `None=讀不到 / ""=空` 全程一致。
