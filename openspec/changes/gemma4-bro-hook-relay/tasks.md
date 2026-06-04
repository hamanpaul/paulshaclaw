# Tasks

> Detailed TDD steps with exact code: `docs/superpowers/plans/2026-06-04-gemma4-bro-hook-relay.md`.

## 1. reply_bridge chunking

- [ ] 1.1 Write failing tests for `_chunk_text` (long split on newline; short stays single) in `tests/test_telegram_reply.py`
- [ ] 1.2 Add `_chunk_text` + chunked send loop in `custom-skills/bro/scripts/reply_bridge.py`; run tests green; commit

## 2. bro_in hook (UserPromptSubmit)

- [ ] 2.1 Write failing tests in `tests/test_gemma4_bro_hooks.py` (bro prompt writes user_id; non-bro clears statefile; missing session_id noop)
- [ ] 2.2 Create `scripts/gemma4-hooks/bro_in.py` (`handle` + `main`, exit 0, log); run tests green; chmod +x; commit

## 3. bro_out hook (Stop)

- [ ] 3.1 Write failing tests (sends last assistant text to stashed user + consumes statefile; empty→notice; no statefile→noop; stop_hook_active→noop)
- [ ] 3.2 Create `scripts/gemma4-hooks/bro_out.py` (`last_assistant_text`, `_send_via_bridge`, `handle`, `main`); run tests green; chmod +x; commit

## 4. daemon back to lean

- [ ] 4.1 Update `tests/test_stage1_smoke.py` assertion to lean `[bro:1001] 請幫我整理狀態`
- [ ] 4.2 Make `route_to_agent` send lean `[bro:<id>] <text>` (drop directive); run tests green; commit

## 5. launcher hook injection

- [ ] 5.1 Write failing packaging tests (`launcher injects bro hooks`; `bro hook scripts packaged + py_compile`)
- [ ] 5.2 Add idempotent `node` hook-injection block to `scripts/claude-gemma4`; `bash -n` + tests green; commit

## 6. bro skill: drop [bro:] auto-trigger

- [ ] 6.1 Remove `[bro:<user_id>]` auto-trigger from `custom-skills/bro/SKILL.md` (description + When-to-use); verify no `[bro:` trigger text remains; commit

## 7. integrate + PR

- [ ] 7.1 Run full `python3 -m pytest tests/ -q` green
- [ ] 7.2 Push branch `feature/gemma4-bro-hook-relay`, open PR, confirm `policy / check` passes

## 8. deploy (post-merge, coordinate with operator)

- [ ] 8.1 Sync runtime/canonical `reply_bridge.py` + `SKILL.md` in `hamanpaul/custom-skills`; open its PR
- [ ] 8.2 Restart stage1 (lean daemon live)
- [ ] 8.3 Restart claude-gemma4 session (loads injected hooks + refreshed skill list)
- [ ] 8.4 End-to-end: one Telegram message → exactly one reply (no duplicate); non-bro → no relay; `bro-hook.log` clean
