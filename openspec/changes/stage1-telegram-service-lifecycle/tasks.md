## 1. Telegram Listener Runtime

- [ ] 1.1 Add offline tests for Telegram API client `getMe`, `getUpdates`, and `sendMessage` request/response handling.
- [ ] 1.2 Implement the standard-library Telegram API client and response validation.
- [ ] 1.3 Add listener tests for authorized text routing, unauthorized handling, non-text handling, and single `sendMessage` behavior.
- [ ] 1.4 Implement `python -m paulshaclaw.bot.listener` with `--config`, token loading, bot identity checks, long polling, offset handling, and bounded backoff.

## 2. Dispatch Guard

- [ ] 2.1 Add tests proving integrated Telegram startup does not report `/dispatch` success through `LocalCoordinator`.
- [ ] 2.2 Implement the production-safe coordinator-not-configured path for Telegram listener startup while preserving explicit fake coordinator injection in unit tests.

## 3. Local Startup Lifecycle

- [ ] 3.1 Extend `tests/test_start_sh.py` to expect monitor, Telegram listener, and cockpit startup.
- [ ] 3.2 Update `scripts/start.sh` to track monitor and Telegram listener PIDs, write Telegram logs to `~/.agents/log/telegram.log`, and terminate background services on cockpit exit, Ctrl+C, or TERM.

## 4. Deploy Templates And Docs

- [ ] 4.1 Extend Stage 7 deploy tests to require Telegram systemd, runtime env, and secret env template assets.
- [ ] 4.2 Add Telegram deploy templates and update `paulshaclaw.deploy` template catalog.
- [ ] 4.3 Update recovery documentation with the actual Telegram service name, log path, token/config checks, and `/dispatch` guard behavior.

## 5. Verification

- [ ] 5.1 Run focused tests for Stage 1 Telegram listener, start script lifecycle, and Stage 7 deploy templates.
- [ ] 5.2 Run the broader unittest discovery suite where the environment supports it, and record any environment-only failures separately.
