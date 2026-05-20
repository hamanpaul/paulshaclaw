## 1. Chat Backend

- [x] 1.1 Add failing offline tests for OpenAI-compatible provider env parsing, request payload construction, response extraction, and sanitized failures.
- [x] 1.2 Implement the `paulshaclaw.chat` module with a `ChatBackend` protocol, OpenAI-compatible client, env-backed factory, timeout handling, and secret-safe errors.

## 2. Telegram Chat Routing

- [x] 2.1 Add failing Telegram router/listener tests proving authorized non-slash text uses chat backend, slash commands keep using daemon commands, and unauthorized users cannot chat.
- [x] 2.2 Update `TelegramCommandRouter` and listener construction to inject the chat backend while preserving existing command behavior and production dispatch guard behavior.

## 3. Provider Placeholder Configuration

- [x] 3.1 Add failing config/sample tests for reserved `chat.providers.openai_compatible`, `chat.providers.gemini_api`, and `chat.providers.copilot_oauth` shape.
- [x] 3.2 Update `paulshaclaw/config/paulshaclaw.sample.yaml` with inactive Gemini and Copilot placeholder provider entries and active OpenAI-compatible env-backed defaults.

## 4. Verification And Completion

- [x] 4.1 Run focused Stage 1 chat, Telegram listener, and config tests.
- [x] 4.2 Run full `python3 -m unittest discover -s tests -v`.
- [x] 4.3 Manually verify local vLLM `/v1/models` and `/v1/chat/completions` with `gemma4-31b-mtp`.
- [x] 4.4 Mark OpenSpec tasks complete and record verification summary in the change directory.

## Verification Summary

- Focused regression: `python -m unittest tests.test_stage1_chat_backend tests.test_stage7_deploy_three_plane tests.test_telegram_listener tests.test_stage1_smoke -v`
- Full suite: `python -m unittest discover -s tests -v`
- Manual vLLM verification:
  - `GET http://192.168.199.199:8000/v1/models` returned `gemma4-31b-mtp`
  - Router-backed `POST /v1/chat/completions` checks succeeded after raising the default timeout to 180 seconds and constraining replies with a concise system prompt plus `max_tokens=256`
