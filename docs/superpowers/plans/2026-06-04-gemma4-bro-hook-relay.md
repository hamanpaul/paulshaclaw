# claude-gemma4 bro hook relay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically relay a claude-gemma4 turn's final reply back to the source Telegram user when the prompt arrived as `[bro:<id>] …`, using Claude Code hooks — no in-prompt directive, no model skill-invocation.

**Architecture:** A `UserPromptSubmit` hook (`bro_in.py`) records the source `user_id` to a per-session statefile when it sees `[bro:<id>]`; a `Stop` hook (`bro_out.py`) reads that statefile, extracts the turn's final assistant text from the transcript, and sends it via `reply_bridge.py --source-user-id <id>`. The claude-gemma4 launcher idempotently injects both hooks into `~/.claude-gemma4/settings.json` (repo = runtime). `reply_bridge.py` gains >4096-char chunking. The daemon drops its directive; the bro skill loses its `[bro:]` auto-trigger (to avoid double replies).

**Tech Stack:** Python 3.12, Claude Code hooks (settings.json), bash launcher, tmux, unittest/pytest.

Spec: `docs/superpowers/specs/2026-06-04-gemma4-bro-hook-relay-design.md`

---

## File structure

- Create `scripts/gemma4-hooks/bro_in.py` — UserPromptSubmit hook: parse `[bro:<id>]`, write/clear statefile.
- Create `scripts/gemma4-hooks/bro_out.py` — Stop hook: read statefile + transcript, send final reply.
- Create `tests/test_gemma4_bro_hooks.py` — unit tests for both hook modules (loaded by path).
- Modify `custom-skills/bro/scripts/reply_bridge.py` — add `_chunk_text` + chunked send.
- Modify `tests/test_telegram_reply.py` — chunking test (this file already exercises reply_bridge).
- Modify `paulshaclaw/core/daemon.py` — `route_to_agent` back to lean `[bro:<id>] <text>`.
- Modify `tests/test_stage1_smoke.py` — assertion back to lean.
- Modify `custom-skills/bro/SKILL.md` — remove `[bro:<id>]` auto-trigger description/bullet.
- Modify `scripts/claude-gemma4` — idempotent hook injection into settings.json.
- Modify `tests/test_claude_gemma4_packaging.py` — assert launcher injects the hooks.

> **Dual-copy note:** `reply_bridge.py` and `SKILL.md` exist both in this repo (`custom-skills/bro/…`, tracked) and in the runtime repo `~/.agents/skills/bro/…` → `/home/paul_chen/prj_pri/custom-skills/bro/…`. Edit the paulshaclaw copy under TDD here; Task 8 syncs the runtime/canonical copy and opens the custom-skills PR.

> **Template note (refinement of spec §6):** the committed `config/claude-gemma4-settings.json` template is left WITHOUT hook paths (absolute repo paths would be brittle/wrong if the repo moves). The launcher injection (Task 6, using `$SCRIPT_DIR`) is the authoritative source of the hooks at runtime.

---

## Task 1: reply_bridge.py — chunk replies over Telegram's length limit

**Files:**
- Modify: `custom-skills/bro/scripts/reply_bridge.py`
- Test: `tests/test_telegram_reply.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_telegram_reply.py` (it already imports the bridge module; mirror its existing import style):

```python
def test_chunk_text_splits_long_text_on_newline(self):
    bridge = load_reply_bridge()  # use the file's existing module loader
    long_text = ("a" * 3000) + "\n" + ("b" * 3000)
    chunks = bridge._chunk_text(long_text, limit=4000)
    self.assertEqual(len(chunks), 2)
    self.assertTrue(all(len(c) <= 4000 for c in chunks))
    self.assertEqual("".join(chunks).replace("\n", ""), long_text.replace("\n", ""))

def test_chunk_text_keeps_short_text_single(self):
    bridge = load_reply_bridge()
    self.assertEqual(bridge._chunk_text("hi", limit=4000), ["hi"])
```

If `tests/test_telegram_reply.py` lacks a module loader, add one near the top mirroring `test_claude_gemma4_packaging.py`:

```python
from importlib.machinery import SourceFileLoader
import importlib.util
REPLY_BRIDGE = Path(__file__).resolve().parents[1] / "custom-skills" / "bro" / "scripts" / "reply_bridge.py"
def load_reply_bridge():
    loader = SourceFileLoader("reply_bridge", str(REPLY_BRIDGE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module); return module
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_telegram_reply.py -k chunk -v`
Expected: FAIL — `AttributeError: module 'reply_bridge' has no attribute '_chunk_text'`

- [ ] **Step 3: Add `_chunk_text` and use it in the send loop**

In `custom-skills/bro/scripts/reply_bridge.py`, add near the top (after imports/constants):

```python
TELEGRAM_TEXT_LIMIT = 4000


def _chunk_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split text into <=limit pieces, preferring newline boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks
```

Then change the send loop (currently lines ~213-214):

```python
    for target in targets:
        for chunk in _chunk_text(text):
            client.send_message(chat_id=target.chat_id, text=chunk)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_telegram_reply.py -v`
Expected: PASS (chunk tests + existing reply tests still green)

- [ ] **Step 5: Commit**

```bash
git add custom-skills/bro/scripts/reply_bridge.py tests/test_telegram_reply.py
git commit -m "feat(bro): reply_bridge 超過 Telegram 上限時自動分段"
```

---

## Task 2: bro_in.py — UserPromptSubmit hook

**Files:**
- Create: `scripts/gemma4-hooks/bro_in.py`
- Test: `tests/test_gemma4_bro_hooks.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gemma4_bro_hooks.py`:

```python
import importlib.util
import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "scripts" / "gemma4-hooks"

def _load(name):
    loader = SourceFileLoader(name, str(HOOKS / f"{name}.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

class BroInTests(unittest.TestCase):
    def setUp(self):
        self.bro_in = _load("bro_in")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def test_bro_prompt_writes_user_id(self):
        self.bro_in.handle({"session_id": "s1", "prompt": "[bro:8313353234] 早安"}, self.state)
        data = json.loads((self.state / "s1.json").read_text(encoding="utf-8"))
        self.assertEqual(data["user_id"], 8313353234)

    def test_non_bro_prompt_clears_existing_statefile(self):
        (self.state / "s1.json").write_text('{"user_id": 1}', encoding="utf-8")
        self.bro_in.handle({"session_id": "s1", "prompt": "hello"}, self.state)
        self.assertFalse((self.state / "s1.json").exists())

    def test_missing_session_id_is_noop(self):
        self.bro_in.handle({"prompt": "[bro:1] hi"}, self.state)
        self.assertEqual(list(self.state.glob("*.json")), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_gemma4_bro_hooks.py -k BroIn -v`
Expected: FAIL — file `scripts/gemma4-hooks/bro_in.py` does not exist.

- [ ] **Step 3: Write `scripts/gemma4-hooks/bro_in.py`**

```python
#!/usr/bin/env python3
"""UserPromptSubmit hook: stash the source Telegram user_id for [bro:<id>] prompts."""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

BRO_RE = re.compile(r"^\s*\[bro:(\d+)\]")
DEFAULT_STATE_DIR = Path.home() / ".agents" / "state" / "bro-hook"
LOG = Path.home() / ".agents" / "log" / "bro-hook.log"


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} bro_in {stage}: {exc!r}\n")
    except Exception:
        pass


def handle(event: dict, state_dir: Path) -> None:
    session_id = str(event.get("session_id") or "").strip()
    if not session_id:
        return
    sf = state_dir / f"{session_id}.json"
    match = BRO_RE.match(event.get("prompt") or "")
    if match:
        state_dir.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps({"user_id": int(match.group(1)), "ts": datetime.datetime.now().isoformat()}),
            encoding="utf-8",
        )
    else:
        sf.unlink(missing_ok=True)


def main() -> int:
    try:
        handle(json.load(sys.stdin), DEFAULT_STATE_DIR)
    except Exception as exc:  # hook must never break the agent
        _log("main", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_gemma4_bro_hooks.py -k BroIn -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/gemma4-hooks/bro_in.py
git add scripts/gemma4-hooks/bro_in.py tests/test_gemma4_bro_hooks.py
git commit -m "feat(stage1): bro_in UserPromptSubmit hook 記錄 [bro:<id>] source user_id"
```

---

## Task 3: bro_out.py — Stop hook

**Files:**
- Create: `scripts/gemma4-hooks/bro_out.py`
- Test: `tests/test_gemma4_bro_hooks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gemma4_bro_hooks.py`:

```python
class BroOutTests(unittest.TestCase):
    def setUp(self):
        self.bro_out = _load("bro_out")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.sent = []

    def _sender(self, user_id, text):
        self.sent.append((user_id, text))

    def _transcript(self, records):
        p = Path(self.tmp.name) / "t.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        return p

    def test_sends_last_assistant_text_to_stashed_user(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "first"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "final answer"}]}},
        ])
        sent = self.bro_out.handle(
            {"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender
        )
        self.assertTrue(sent)
        self.assertEqual(self.sent, [(7, "final answer")])
        self.assertFalse((self.state / "s1.json").exists())  # consumed

    def test_empty_final_text_sends_notice(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        t = self._transcript([
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "x", "input": {}}]}},
        ])
        self.bro_out.handle({"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender)
        self.assertEqual(self.sent, [(7, "（已完成，無文字輸出）")])

    def test_no_statefile_is_noop(self):
        t = self._transcript([{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}])
        self.assertFalse(self.bro_out.handle({"session_id": "s1", "transcript_path": str(t)}, self.state, sender=self._sender))
        self.assertEqual(self.sent, [])

    def test_stop_hook_active_is_noop(self):
        (self.state / "s1.json").write_text('{"user_id": 7}', encoding="utf-8")
        self.assertFalse(self.bro_out.handle({"session_id": "s1", "stop_hook_active": True}, self.state, sender=self._sender))
        self.assertEqual(self.sent, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_gemma4_bro_hooks.py -k BroOut -v`
Expected: FAIL — `scripts/gemma4-hooks/bro_out.py` does not exist.

- [ ] **Step 3: Write `scripts/gemma4-hooks/bro_out.py`**

```python
#!/usr/bin/env python3
"""Stop hook: relay the turn's final assistant text to the bro Telegram user."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".agents" / "state" / "bro-hook"
REPLY_BRIDGE = Path.home() / ".agents" / "skills" / "bro" / "scripts" / "reply_bridge.py"
LOG = Path.home() / ".agents" / "log" / "bro-hook.log"
EMPTY_NOTICE = "（已完成，無文字輸出）"


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} bro_out {stage}: {exc!r}\n")
    except Exception:
        pass


def last_assistant_text(transcript_path: Path) -> str:
    text = ""
    for line in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, list):
            joined = "".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if joined:
                text = joined
        elif isinstance(content, str) and content.strip():
            text = content.strip()
    return text


def _send_via_bridge(user_id: int, text: str) -> None:
    subprocess.run(
        [sys.executable, str(REPLY_BRIDGE), "--source-user-id", str(user_id), "--text", text],
        check=False,
    )


def handle(event: dict, state_dir: Path, sender=_send_via_bridge) -> bool:
    if event.get("stop_hook_active"):
        return False
    session_id = str(event.get("session_id") or "").strip()
    if not session_id:
        return False
    sf = state_dir / f"{session_id}.json"
    if not sf.exists():
        return False
    try:
        user_id = int(json.loads(sf.read_text(encoding="utf-8"))["user_id"])
    except Exception as exc:
        _log("statefile", exc)
        sf.unlink(missing_ok=True)
        return False
    tp = event.get("transcript_path")
    text = ""
    if tp and Path(tp).exists():
        try:
            text = last_assistant_text(Path(tp))
        except Exception as exc:
            _log("transcript", exc)
    try:
        sender(user_id, text or EMPTY_NOTICE)
    except Exception as exc:
        _log("send", exc)
    sf.unlink(missing_ok=True)
    return True


def main() -> int:
    try:
        handle(json.load(sys.stdin), DEFAULT_STATE_DIR)
    except Exception as exc:  # hook must never break the agent
        _log("main", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_gemma4_bro_hooks.py -v`
Expected: PASS (BroIn + BroOut)

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/gemma4-hooks/bro_out.py
git add scripts/gemma4-hooks/bro_out.py tests/test_gemma4_bro_hooks.py
git commit -m "feat(stage1): bro_out Stop hook 把最終回覆送回 bro Telegram 使用者"
```

---

## Task 4: daemon route_to_agent — back to lean

**Files:**
- Modify: `paulshaclaw/core/daemon.py` (route_to_agent, ~lines 234-244)
- Test: `tests/test_stage1_smoke.py` (~line 233)

- [ ] **Step 1: Update the test to expect the lean message**

Replace the assertion:

```python
        send_mock.assert_called_once_with("%9", "[bro:1001] 請幫我整理狀態")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stage1_smoke.py -k route_to_agent -v`
Expected: FAIL — current code still appends `｜用 bro skill 回 …`.

- [ ] **Step 3: Make route_to_agent lean**

In `paulshaclaw/core/daemon.py`, replace the directive block with:

```python
        pane_id, _pid = detected
        self._agent_pane_id = pane_id
        # Lean tag only; the gemma4 bro hooks (UserPromptSubmit/Stop) handle the
        # Telegram reply deterministically, so no in-prompt directive is needed.
        self._send_to_pane(pane_id, f"[bro:{user_id}] {text}")
        return "…"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_stage1_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/core/daemon.py tests/test_stage1_smoke.py
git commit -m "refactor(stage1): route_to_agent 回精簡 [bro:<id>]，回覆改由 hook 處理"
```

---

## Task 5: launcher — idempotent hook injection

**Files:**
- Modify: `scripts/claude-gemma4` (after the existing `.claude.json` node block, before the `unset` lines)
- Test: `tests/test_claude_gemma4_packaging.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_claude_gemma4_packaging.py` (string-presence, matching the file's existing launcher tests):

```python
def test_launcher_injects_bro_hooks(self) -> None:
    script_text = CLAUDE_GEMMA4.read_text(encoding="utf-8")
    self.assertIn("gemma4-hooks/bro_in.py", script_text)
    self.assertIn("gemma4-hooks/bro_out.py", script_text)
    self.assertIn("UserPromptSubmit", script_text)
    self.assertIn("Stop", script_text)
```

Also assert the hook scripts ship and are executable:

```python
def test_bro_hook_scripts_packaged(self) -> None:
    for name in ("bro_in.py", "bro_out.py"):
        p = PROJECT_ROOT / "scripts" / "gemma4-hooks" / name
        self.assertTrue(p.exists(), f"{name} should exist")
        self.assertTrue(os.access(p, os.X_OK), f"{name} should be executable")
        r = subprocess.run(["python3", "-m", "py_compile", str(p)], capture_output=True, text=True, timeout=5)
        self.assertEqual(r.returncode, 0, r.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_claude_gemma4_packaging.py -k bro_hook -v`
Expected: FAIL — launcher has no hook injection yet.

- [ ] **Step 3: Add the injection block to `scripts/claude-gemma4`**

Insert after the existing `node - "$GEMMA_CONFIG_DIR/.claude.json" …` block:

```bash
# Idempotently ensure the gemma4 bro hooks are wired into settings.json
# (repo = runtime; absolute paths resolved from this launcher's SCRIPT_DIR).
node - "$GEMMA_SETTINGS" "$SCRIPT_DIR/gemma4-hooks/bro_in.py" "$SCRIPT_DIR/gemma4-hooks/bro_out.py" <<'NODE'
const fs = require('fs');
const [file, broIn, broOut] = process.argv.slice(2);
let cfg = {};
try { cfg = JSON.parse(fs.readFileSync(file, 'utf8')); } catch {}
cfg.hooks = cfg.hooks || {};
cfg.hooks.UserPromptSubmit = [{ hooks: [{ type: 'command', command: `python3 ${broIn}` }] }];
cfg.hooks.Stop = [{ hooks: [{ type: 'command', command: `python3 ${broOut}` }] }];
fs.writeFileSync(file, JSON.stringify(cfg, null, 2) + '\n');
NODE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_claude_gemma4_packaging.py -v && bash -n scripts/claude-gemma4 && echo OK`
Expected: PASS + `OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/claude-gemma4 tests/test_claude_gemma4_packaging.py
git commit -m "feat(stage1): claude-gemma4 launcher 冪等注入 bro in/out hooks"
```

---

## Task 6: bro skill — remove the `[bro:]` auto-trigger (avoid double reply)

**Files:**
- Modify: `custom-skills/bro/SKILL.md`

- [ ] **Step 1: Edit the skill description + When-to-use**

In `custom-skills/bro/SKILL.md`:

- In the `description:` frontmatter, delete the sentence: `ALSO trigger automatically when an incoming message is prefixed with [bro:<user_id>] (routed from the PaulShiaBro daemon): parse <user_id>, complete the request, then reply via this skill with --source-user-id <user_id>.`
- In `## When to use`, delete the bullet beginning `**An incoming message is prefixed with \`[bro:<user_id>]\`** … This is the primary automatic trigger.`

Leave the rest (natural-language "用 bro 回覆" triggers, workflow, reply_bridge usage) intact.

- [ ] **Step 2: Verify no `[bro:` auto-trigger text remains**

Run: `grep -n '\[bro:' custom-skills/bro/SKILL.md || echo "no bro-tag trigger left"`
Expected: `no bro-tag trigger left`

- [ ] **Step 3: Commit**

```bash
git add custom-skills/bro/SKILL.md
git commit -m "refactor(bro): 移除 SKILL.md 的 [bro:] 自動觸發，避免與 hook 雙重回覆"
```

---

## Task 7: full suite + push + PR

- [ ] **Step 1: Run the full repo test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass (existing + new `test_gemma4_bro_hooks.py`, updated packaging/smoke/reply tests).

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feature/gemma4-bro-hook-relay
gh pr create --base main --head feature/gemma4-bro-hook-relay \
  --title 'feat(stage1): gemma4 bro hook relay（UserPromptSubmit+Stop 中轉）' \
  --body-file <(printf '%s\n' '依 spec docs/superpowers/specs/2026-06-04-gemma4-bro-hook-relay-design.md。' '' '- bro_in/bro_out hooks + launcher 冪等注入' '- reply_bridge 分段；daemon 回精簡；skill 移除 [bro:] 自動觸發' '' '🤖 Generated with [Claude Code](https://claude.com/claude-code)')
```

- [ ] **Step 3: Confirm policy CI passes**

Run: `gh pr checks` — expect `policy / check  pass`. Do not merge until green and reviewed.

---

## Task 8: deploy to runtime + custom-skills sync (post-merge)

> Runtime loads from the standalone `hamanpaul/custom-skills` repo, not paulshaclaw. After the paulshaclaw PR merges:

- [ ] **Step 1: Sync the runtime/canonical copies** of `reply_bridge.py` and `SKILL.md` to match the merged paulshaclaw versions:

```bash
cp /home/paul_chen/prj_pri/paulshaclaw/custom-skills/bro/scripts/reply_bridge.py /home/paul_chen/prj_pri/custom-skills/bro/scripts/reply_bridge.py
cp /home/paul_chen/prj_pri/paulshaclaw/custom-skills/bro/SKILL.md /home/paul_chen/prj_pri/custom-skills/bro/SKILL.md
```

- [ ] **Step 2: Commit those in `hamanpaul/custom-skills`** via a clean worktree off `origin/main` (do NOT sweep the user's unrelated WIP), open a PR.

- [ ] **Step 3: Restart stage1** so the lean daemon is live:

```bash
kill -TERM "$(pgrep -f 'bash ./scripts/start.sh' | head -1)"
# wait for monitor/listener/cockpit to exit, then:
tmux send-keys -t %0 './scripts/start.sh' Enter
# verify: 4 procs up + ~/.agents/run/telegram.ready refreshed
```

- [ ] **Step 4: Restart the claude-gemma4 session** (so it (a) loads the injected hooks on launch and (b) reloads the skill list without the `[bro:]` trigger). The launcher injects the hooks into `~/.claude-gemma4/settings.json` on start. This is the user's interactive session — coordinate with the user rather than killing it.

- [ ] **Step 5: End-to-end check** — from Telegram send a non-command message; confirm exactly ONE reply comes back (hook), no duplicate (skill no longer auto-triggers), and that `~/.agents/log/bro-hook.log` shows no errors. A non-`[bro:]` interaction triggers no relay.
