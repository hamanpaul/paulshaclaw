## 1. Chat Backend

- [ ] 1.1 Add failing offline tests for OpenAI-compatible provider env parsing, request payload construction, response extraction, and sanitized failures.
- [ ] 1.2 Implement the `paulshaclaw.chat` module with a `ChatBackend` protocol, OpenAI-compatible client, env-backed factory, timeout handling, and secret-safe errors.

## 2. Telegram Chat Routing

- [ ] 2.1 Add failing Telegram router/listener tests proving authorized non-slash text uses chat backend, slash commands keep using daemon commands, and unauthorized users cannot chat.
- [ ] 2.2 Update `TelegramCommandRouter` and listener construction to inject the chat backend while preserving existing command behavior and production dispatch guard behavior.

## 3. Provider Placeholder Configuration

- [ ] 3.1 Add failing config/sample tests for reserved `chat.providers.openai_compatible`, `chat.providers.gemini_api`, and `chat.providers.copilot_oauth` shape.
- [ ] 3.2 Update `paulshaclaw/config/paulshaclaw.sample.yaml` with inactive Gemini and Copilot placeholder provider entries and active OpenAI-compatible env-backed defaults.

## 4. Verification And Completion

- [ ] 4.1 Run focused Stage 1 chat, Telegram listener, and config tests.
- [ ] 4.2 Run full `python3 -m unittest discover -s tests -v`.
- [ ] 4.3 Manually verify local vLLM `/v1/models` and `/v1/chat/completions` with `gemma4-31b-mtp`.
- [ ] 4.4 Mark OpenSpec tasks complete and record verification summary in the change directory.
