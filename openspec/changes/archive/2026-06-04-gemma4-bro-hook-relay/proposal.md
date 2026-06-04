## Why

Routing a Telegram `[bro:<id>]` message into the claude-gemma4 agent pane only gets a reply back if the small gemma4 model decides to invoke the reply skill — which it does unreliably, and propping it up with an in-prompt directive wastes context every dispatch. We need the reply to be delivered **deterministically** without depending on the model's reasoning or polluting the prompt.

## What Changes

- Add two Claude Code hooks for claude-gemma4 that perform the Telegram relay deterministically (run by the CLI, model-agnostic):
  - `UserPromptSubmit` (`bro_in`): detect `[bro:<id>]` and record the source `user_id` to a per-session statefile.
  - `Stop` (`bro_out`): on turn end, read the statefile + the transcript's final assistant text and send it via `reply_bridge.py --source-user-id <id>`; non-`[bro:]` turns do nothing.
- `reply_bridge.py`: chunk replies that exceed Telegram's ~4096-char limit.
- **BREAKING (internal routing):** daemon `route_to_agent` reverts to the lean `[bro:<id>] <text>` (drops the per-message reply directive).
- `bro` skill: remove its `[bro:<id>]` auto-trigger from `SKILL.md` so the model no longer also invokes it (avoids double replies); the skill stays for natural-language "用 bro 回覆".
- claude-gemma4 launcher idempotently injects both hooks into `~/.claude-gemma4/settings.json` on each start (repo = runtime).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `agent-conversation-routing`: the routed message reverts to lean `[bro:<user_id>] <text>`; the reply back to Telegram is now delivered deterministically by claude-gemma4 hooks rather than by a per-message directive or model-invoked skill.

## Impact

- Code: `scripts/gemma4-hooks/bro_in.py`, `scripts/gemma4-hooks/bro_out.py` (new); `scripts/claude-gemma4` (hook injection); `paulshaclaw/core/daemon.py` (`route_to_agent`); `custom-skills/bro/scripts/reply_bridge.py` (chunking); `custom-skills/bro/SKILL.md` (drop `[bro:]` trigger).
- Runtime: hooks land in `~/.claude-gemma4/settings.json`; statefiles under `~/.agents/state/bro-hook/`; logs to `~/.agents/log/bro-hook.log`. Requires a stage1 restart (lean daemon) and a claude-gemma4 session restart (load hooks + refreshed skill list).
- External repo: `hamanpaul/custom-skills` (runtime copy of `reply_bridge.py` + `SKILL.md`) must be synced.
- Tests: `tests/test_gemma4_bro_hooks.py` (new); updates to `tests/test_telegram_reply.py`, `tests/test_stage1_smoke.py`, `tests/test_claude_gemma4_packaging.py`.
