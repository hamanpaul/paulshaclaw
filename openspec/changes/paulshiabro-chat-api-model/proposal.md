## Why

PaulShiaBro Stage 1 currently treats every Telegram text message as a slash command, so ordinary operator conversation returns an unsupported-command error. The local vLLM endpoint is now verified healthy, making it practical to add API-model-backed conversation without changing the existing command surface.

## What Changes

- Add Telegram non-slash conversation support for authorized users.
- Keep `/status`, `/dispatch`, `/tmate`, `/help`, and pane dispatch behavior on the existing command dispatcher path.
- Add a small chat backend abstraction and implement only the local OpenAI-compatible vLLM provider.
- Load the initial provider from `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`.
- Reserve schema placeholders for Gemini API and GitHub Copilot OAuth without implementing those runtime clients.
- Reserve a guarded tool bridge interface, disabled by default, for future natural-language-to-command mapping.

## Capabilities

### New Capabilities

None. This change extends the existing Stage 1 Telegram/runtime capability instead of introducing a separate top-level capability.

### Modified Capabilities

- `stage1-core-runtime`: Add authorized Telegram non-slash chat routing, local OpenAI-compatible chat backend behavior, and provider-placeholder requirements while preserving existing slash command behavior.

## Impact

- Affected runtime code: `paulshaclaw/bot/telegram.py`, `paulshaclaw/bot/listener.py`, new `paulshaclaw/chat/` module.
- Affected config: `paulshaclaw/config/paulshaclaw.sample.yaml` gains reserved chat provider shape.
- Affected tests: Stage 1 Telegram router/listener tests and new chat backend/client tests.
- Dependencies: no new third-party dependency; the OpenAI-compatible client uses Python standard library HTTP handling.
- External system: local vLLM server at `http://192.168.199.199:8000/v1`, model `gemma4-31b-mtp`.
