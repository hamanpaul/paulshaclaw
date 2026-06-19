## Context

Stage 1 already has a clear Telegram command path: `TelegramListener` receives updates, `TelegramCommandRouter` authorizes users, and `PaulShiaBroDaemon` executes slash commands through the command registry. The gap is ordinary non-slash conversation; today it reaches `handle_command()` and fails as an unsupported command.

The local vLLM server has been manually verified on 2026-05-20. `GET /v1/models` exposes `gemma4-31b-mtp`, and `POST /v1/chat/completions` returns a valid assistant message. The implementation can therefore use the OpenAI-compatible chat endpoint directly.

## Goals / Non-Goals

**Goals:**

- Add authorized Telegram non-slash conversation backed by local vLLM.
- Preserve all existing slash command behavior and command tests.
- Keep the chat provider implementation small, testable, and standard-library only.
- Keep provider credentials out of output and persistent logs.
- Reserve inactive Gemini API and GitHub Copilot OAuth provider shapes.

**Non-Goals:**

- No cockpit or TUI chat surface.
- No coordinator worker or `/dispatch` behavior change.
- No model-driven arbitrary tool execution.
- No conversation memory beyond the current Telegram message.
- No OpenAI SDK dependency.
- No runtime Gemini or Copilot client in this change.

## Decisions

### Route chat in `TelegramCommandRouter`

`TelegramCommandRouter.handle_message()` remains the authorization boundary. After authorization, it will branch by message shape:

- `text.lstrip().startswith("/")` uses the existing `daemon.handle_command(text)` path.
- Other text calls an injected `ChatBackend`.

Alternative considered: add `PaulShiaBroDaemon.handle_message()`. That would make future TUI reuse simpler, but it expands the daemon contract and mixes command runtime with chat transport behavior before another transport needs it.

### Use a small `ChatBackend` protocol

The router should depend on a narrow protocol such as `reply(user_id: int, text: str) -> str`. This keeps tests simple and prevents the router from knowing HTTP details.

The concrete local backend will build a short system/user message list and call the OpenAI-compatible API.

### Use stdlib HTTP instead of the OpenAI SDK

The repo already favors small standard-library adapters for Telegram. A `urllib.request` based OpenAI-compatible client avoids adding dependency and event-loop concerns for one endpoint.

Alternative considered: OpenAI Python SDK. It reduces request boilerplate, but adds dependency and version churn while the local endpoint only needs `/chat/completions`.

### Load initial provider from environment

The working deployment already provides:

```text
OPENAI_BASE_URL=http://192.0.2.10:8000/v1
OPENAI_API_KEY=dummy
OPENAI_MODEL=gemma4-31b-mtp
```

The implementation should read these env vars first. The global sample config can reserve the future provider registry shape, but it should not become mandatory for this first integration.

### Reserve but disable tool bridge

The model will not execute tools in this change. A future `ToolBridge` can map explicit model intents to existing daemon commands behind an allowlist and optional confirmation gate. This design avoids granting the model open shell or dispatcher access.

## Risks / Trade-offs

- vLLM outage or timeout -> return sanitized `chat backend 逾時` or `chat backend 未設定` style messages.
- Provider error could leak secrets -> never include request headers, API key, or full request body in user-facing errors.
- Non-slash messages might accidentally trigger tools -> no tool bridge is enabled in this change.
- Chat backend could slow Telegram polling -> use bounded per-request timeout and keep the existing listener backoff behavior.
- Model replies can be long -> cap `max_tokens` to a concise Telegram-friendly default and return the assistant content only.

## Migration Plan

1. Add offline failing tests for router chat branching and OpenAI-compatible client behavior.
2. Implement the chat module and inject it into Telegram listener construction.
3. Add reserved chat provider shape to the sample config.
4. Run focused tests and full unittest discovery.
5. Manually verify the local vLLM endpoint with `/v1/models` and `/v1/chat/completions`.

Rollback is removing the new chat module, router injection, config sample section, and tests. Existing slash command behavior remains the fallback path.

## Open Questions

No blocking questions remain. Gemini API and Copilot OAuth implementation details are intentionally deferred.
