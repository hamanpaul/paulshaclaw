## 1. Telegram Listener Runtime

- [x] 1.1 Add offline tests for Telegram API client `getMe`, `getUpdates`, and `sendMessage` request/response handling.
- [x] 1.2 Implement the standard-library Telegram API client and response validation.
- [x] 1.3 Add listener tests for authorized text routing, unauthorized handling, non-text handling, and single `sendMessage` behavior.
- [x] 1.4 Implement `python -m paulshaclaw.bot.listener` with `--config`, token loading, bot identity checks, long polling, offset handling, and bounded backoff.

## 2. Dispatch Guard

- [x] 2.1 Add tests proving integrated Telegram startup does not report `/dispatch` success through `LocalCoordinator`.
- [x] 2.2 Implement the production-safe coordinator-not-configured path for Telegram listener startup while preserving explicit fake coordinator injection in unit tests.

## 3. Local Startup Lifecycle

- [x] 3.1 Extend `tests/test_start_sh.py` to expect monitor, Telegram listener, and cockpit startup.
- [x] 3.2 Update `scripts/start.sh` to track monitor and Telegram listener PIDs, write Telegram logs to `~/.agents/log/telegram.log`, and terminate background services on cockpit exit, Ctrl+C, or TERM.

## 4. Deploy Templates And Docs

- [x] 4.1 Extend Stage 7 deploy tests to require Telegram systemd, runtime env, and secret env template assets.
- [x] 4.2 Add Telegram deploy templates and update `paulshaclaw.deploy` template catalog.
- [x] 4.3 Update recovery documentation with the actual Telegram service name, log path, token/config checks, and `/dispatch` guard behavior.

## 5. Verification

- [x] 5.1 Run focused tests for Stage 1 Telegram listener, start script lifecycle, and Stage 7 deploy templates.
- [x] 5.2 Run the broader unittest discovery suite where the environment supports it, and record any environment-only failures separately.
  - Environment-only failure during `python -m unittest discover -s tests -v`: `test_stage9_project_monitor.Stage9SnapshotTests.test_paulshaclaw_self_snapshot_matches_known_state` expects a worktree name containing `paulshaclaw` or `stage9-project-monitor` under the current `.worktrees` workspace root. In this environment the visible worktrees are `stage1-telegram-service-lifecycle` and `stage11-multi-session`, so the assertion fails independently of the Telegram lifecycle changes.
