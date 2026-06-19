## Context

PaulShiaBro's daemon routes non-command Telegram messages into the claude-gemma4 agent pane as `[bro:<id>] <text>` (`paulshaclaw/core/daemon.py:route_to_agent`). Getting the reply back currently depends on the small gemma4 model invoking the `bro`/reply skill. Observed in session transcripts: a bare `[bro:]` tag is treated as chat (no skill invocation); only an explicit per-message directive reliably triggers it. That directive costs context on every dispatch. claude-gemma4 is Claude Code with `CLAUDE_CONFIG_DIR=~/.claude-gemma4` and a custom model backend (vLLM via proxy); hooks are executed by the CLI regardless of model.

Full design background: `docs/superpowers/specs/2026-06-04-gemma4-bro-hook-relay-design.md`.

## Goals / Non-Goals

**Goals:**
- Deterministic Telegram reply for `[bro:<id>]` turns, independent of the model's reasoning.
- No in-prompt directive (zero token cost on the routed message).
- Non-`[bro:]` turns cause no relay.

**Non-Goals:**
- Headless `-p` relay architecture (rejected; keeps the live interactive pane).
- Cross-session conversation memory, retry queues, or persistent message dedup.
- Changing the natural-language "用 bro 回覆" skill path.

## Decisions

- **Two hooks + per-session statefile (chosen) over a single Stop hook parsing the transcript.** `UserPromptSubmit` (`bro_in`) gets the raw prompt directly and records `user_id` to `~/.agents/state/bro-hook/<session_id>.json`; `Stop` (`bro_out`) consumes it. Alternative (single Stop hook deriving `[bro:<id>]` from the transcript) needs to filter `tool_result` records (also `user` role) and makes "in" implicit — more fragile.
- **Output captured from the structured transcript, not the rendered pane.** The TUI redraws/streams; the jsonl transcript has clean assistant `text` blocks. `bro_out` takes the last `assistant` record's concatenated text.
- **Launcher injects hooks idempotently** into `~/.claude-gemma4/settings.json` using `$SCRIPT_DIR` absolute paths (repo = runtime). The committed settings template is left pathless to avoid brittle hardcoded repo paths.
- **Hooks always `exit 0`** and log to `~/.agents/log/bro-hook.log`; a hook must never block the agent.
- **Remove the skill's `[bro:]` auto-trigger** so the model does not also invoke the skill and produce a duplicate reply.

## Risks / Trade-offs

- [Duplicate reply if the skill still auto-triggers] → remove the `[bro:]` trigger from `SKILL.md` (Task 6).
- [Hook fires on a turn that stopped to ask a clarifying question] → that question is sent to Telegram; the user's reply returns as the next `[bro:]` turn. Accepted (natural conversation).
- [`stop_hook_active` re-trigger loop] → `bro_out` returns immediately when `stop_hook_active` is set.
- [Stale statefile causing a spurious send] → `bro_in` clears the statefile on any non-`[bro:]` prompt; `bro_out` deletes after use.
- [Reply over Telegram's 4096-char limit] → `reply_bridge.py` chunks on newline boundaries.

## Migration Plan

1. Merge the paulshaclaw PR (hooks, lean daemon, launcher injection, skill edit, tests).
2. Sync the runtime/canonical copies of `reply_bridge.py` + `SKILL.md` in `hamanpaul/custom-skills`; open its PR.
3. Restart stage1 (lean daemon live).
4. Restart the claude-gemma4 session (launcher injects hooks on start; skill list refreshes).
5. Rollback: remove the `hooks` block from `~/.claude-gemma4/settings.json` (or revert the launcher injection) and restore the daemon directive — fully reversible, no data migration.

## Open Questions

None — design approved during brainstorming.
