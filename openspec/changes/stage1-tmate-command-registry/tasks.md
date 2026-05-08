## 1. Command Registry Foundation

- [ ] 1.1 Add `paulshaclaw/core/commands.json` with `/help`, `/status`, `/dispatch`, and `/tmate` metadata.
- [ ] 1.2 Add registry loader and validation for command uniqueness, Telegram menu constraints, Python targets, shell argv, placeholders, and timeouts.
- [ ] 1.3 Add registry-backed dispatcher with explicit Python handler map and safe shell argv execution.
- [ ] 1.4 Route existing `/status` and `/dispatch` behavior through the dispatcher without changing their public response contracts.

## 2. Help And Telegram Menu

- [ ] 2.1 Implement `/help` list and single-command output generated from `commands.json`.
- [ ] 2.2 Add Telegram API client support for `setMyCommands` and `getMyCommands`.
- [ ] 2.3 Sync Telegram command menu from registry after `getMe` and before `getUpdates`.
- [ ] 2.4 Fail listener startup when registry validation or `setMyCommands` fails.

## 3. Tmate Runtime

- [ ] 3.1 Add managed tmate state model under `~/.agents/run/` and `~/.agents/state/`.
- [ ] 3.2 Implement fixed-argv tmate executor for start, status, link readout, attached-client count, and stop.
- [ ] 3.3 Implement `/tmate`, `/tmate status`, `/tmate start`, and `/tmate stop` handlers.
- [ ] 3.4 Implement 3600-second no-client idle timeout cleanup from command handling and Telegram polling.
- [ ] 3.5 Redact tmate links and token-like values from normal Telegram listener logs.

## 4. Tests And Verification

- [ ] 4.1 Add offline unit tests for registry validation, help generation, dispatcher routing, and shell argv execution.
- [ ] 4.2 Add offline listener tests for `setMyCommands` startup order and startup failure handling.
- [ ] 4.3 Add offline tmate tests with fake executor output for lifecycle and idle cleanup.
- [ ] 4.4 Update Stage 1 smoke tests to cover `/help` and registry-backed `/status` and `/dispatch`.
- [ ] 4.5 Run targeted Stage 1 tests and full repository unittest discovery.
