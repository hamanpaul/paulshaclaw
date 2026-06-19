# PaulShiaBro Chat API Model Design

## Context

PaulShiaBro Stage 1 currently routes Telegram text through `TelegramCommandRouter`, then into `PaulShiaBroDaemon.handle_command()`. That keeps slash commands such as `/status`, `/dispatch`, `/tmate`, and `/help` in a clear command dispatcher path, but ordinary non-slash text is treated as an unsupported command.

This change adds API-model-backed conversation for authorized Telegram users while preserving the existing command path. The first runtime provider is the local vLLM server exposed as an OpenAI-compatible API:

```text
OPENAI_BASE_URL=http://192.0.2.10:8001/v1
OPENAI_API_KEY=dummy
OPENAI_MODEL=gemma4-26b-a4b-nvfp4
```

On 2026-05-20, this endpoint was verified with:

- `GET /v1/models`: returned model `gemma4-31b-mtp`, owned by `vllm`, with `max_model_len=8192`.
- `POST /v1/chat/completions`: returned `PaulShiaBro vLLM 健康檢查正常。`.

> Updated 2026-06-01: the vLLM endpoint moved to `http://192.0.2.10:8001/v1` and now serves `gemma4-26b-a4b-nvfp4` (`max_model_len=262144`). The config block and examples in this doc reflect the new endpoint; the 2026-05-20 verification above is kept verbatim as the original record.

The vLLM server is therefore suitable for the initial chat integration. Gemini API and GitHub Copilot OAuth are reserved as future provider shapes only; they are not implemented in this change.

## Confirmed Scope

- Add Telegram non-slash conversation support for authorized users.
- Keep all slash commands on the existing command dispatcher path.
- Implement only the local OpenAI-compatible vLLM provider.
- Do not implement Gemini runtime calls in this change.
- Do not implement GitHub Copilot OAuth or SDK runtime calls in this change.
- Do not let the model execute arbitrary tools.
- Reserve a guarded tool bridge interface for later natural-language-to-command mapping.

## Goals

- Let authorized Telegram users send ordinary text and receive a model response from local vLLM.
- Preserve current command behavior for `/status`, `/dispatch`, `/tmate`, `/help`, and pane dispatch forms.
- Keep provider settings configuration-driven and secret-safe.
- Keep tests offline by using fake HTTP openers and fake chat backends.
- Leave a narrow extension point for Gemini API and Copilot OAuth without adding runtime complexity now.

## Non-Goals

- No cockpit or TUI chat UI.
- No coordinator worker changes.
- No model-driven arbitrary tool execution.
- No conversation memory beyond the current Telegram message.
- No OpenAI Python SDK dependency.
- No real network calls in unit tests.

## Architecture

The new path is a small branch in the Telegram router:

```text
Telegram message
  -> TelegramListener.process_update()
  -> TelegramCommandRouter.handle_message(user_id, text)
      -> unauthorized user: reject
      -> text starts with "/": PaulShiaBroDaemon.handle_command(text)
      -> other text: ChatBackend.reply(user_id=user_id, text=text)
          -> OpenAI-compatible client
          -> POST {OPENAI_BASE_URL}/chat/completions
          -> gemma4-26b-a4b-nvfp4
```

`TelegramCommandRouter` remains the authorization boundary. It does not parse provider config or construct HTTP requests. The daemon remains the command runtime and is not responsible for ordinary chat in this first version.

The chat module boundary is:

```text
paulshaclaw/chat/
  config.py      # provider/env parsing and reserved schema validation
  openai.py      # stdlib urllib OpenAI-compatible client
  backend.py     # ChatBackend protocol and factory
  tools.py       # reserved ToolBridge protocol, disabled by default
```

The names can be adjusted during implementation if the repo's package style suggests a smaller file split, but the responsibilities should stay separate.

## Data Flow

For non-slash text:

1. `TelegramListener` receives the update and extracts `chat_id`, `user_id`, and `text`.
2. `TelegramCommandRouter` rejects unauthorized users before any command or chat backend call.
3. If `text.lstrip().startswith("/")`, the existing command route is used.
4. Otherwise, the router calls `chat_backend.reply(user_id=user_id, text=text)`.
5. The OpenAI-compatible client posts:

```json
{
  "model": "gemma4-26b-a4b-nvfp4",
  "messages": [
    {
      "role": "system",
      "content": "You are PaulShiaBro, a concise assistant for the operator."
    },
    {
      "role": "user",
      "content": "<telegram text>"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 1024
}
```

6. The router returns the assistant message content as the Telegram reply.

The system prompt should be short and local to the chat backend. It should not restate secret values or include broad tool permissions.

## Configuration

The initial runtime loads the local vLLM provider from environment variables:

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

This matches the existing deployment and avoids adding a second required config file before the chat path is proven.

The global sample config should reserve the future shape:

```yaml
chat:
  provider: openai_compatible
  providers:
    openai_compatible:
      base_url_env: OPENAI_BASE_URL
      api_key_env: OPENAI_API_KEY
      model_env: OPENAI_MODEL
      timeout_seconds: 45
      max_tokens: 1024
      temperature: 0.2
    gemini_api:
      enabled: false
      api_key_env: GEMINI_API_KEY
      model: gemini-2.5-flash
    copilot_oauth:
      enabled: false
      token_env: COPILOT_GITHUB_TOKEN
      oauth_config_path: ~/.copilot/config.json
```

Only `openai_compatible` is instantiated. `gemini_api` and `copilot_oauth` are schema placeholders.

Official references support these reserved shapes:

- Gemini provides an OpenAI-compatible endpoint at `https://generativelanguage.googleapis.com/v1beta/openai/`.
- GitHub Copilot CLI supports OAuth device flow and token environment variables such as `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, and `GITHUB_TOKEN`.

## Error Handling

When chat is unavailable:

- Missing provider env returns a clear user-facing message: `chat backend 未設定`.
- HTTP timeout returns `chat backend timeout`.
- Provider HTTP/JSON errors return a short sanitized message.
- Empty model output returns `chat backend 回覆為空`.

No error path may include the API key. Logs should redact secrets and avoid dumping full HTTP request bodies.

## Tool Bridge Reservation

This design reserves but does not enable tool use.

Future tool use must go through a guarded bridge:

```text
model proposes intent
  -> ToolBridge validates against allowlist
  -> optional confirmation gate
  -> existing daemon command executes
```

Initial allowlist candidates:

- read-only status mapped to `/status`
- explicit task dispatch mapped to `/dispatch <task_id>`
- explicit pane message mapped to `/dispatch %pane <message>`

Dispatch-like actions should require confirmation or a strict command-shaped response before execution. Arbitrary shell/tool calling is out of scope.

## Security

- Authorization remains unchanged: only `allowed_user_ids` may use commands or chat.
- API key values are read from env and never printed.
- Telegram outbound logging should continue using redaction.
- The chat backend must not write prompts or full model replies to persistent logs by default.
- The local base URL is treated as trusted operator infrastructure, but failures still degrade cleanly.

## Testing

Unit tests should cover:

- Authorized non-slash Telegram text calls the chat backend and sends one reply.
- Authorized slash commands continue to call the existing daemon command path.
- Unauthorized users call neither daemon commands nor chat backend.
- Missing chat backend returns `chat backend 未設定`.
- OpenAI-compatible client builds `POST /chat/completions` requests with the configured model.
- OpenAI-compatible client extracts `choices[0].message.content`.
- Timeout and malformed JSON errors are sanitized.
- Sample config accepts reserved `gemini_api` and `copilot_oauth` shapes but does not instantiate them.

Manual verification after implementation:

```bash
curl -sS --max-time 10 \
  -H 'Authorization: Bearer dummy' \
  http://192.0.2.10:8001/v1/models

curl -sS --max-time 45 \
  -H 'Authorization: Bearer dummy' \
  -H 'Content-Type: application/json' \
  http://192.0.2.10:8001/v1/chat/completions \
  -d '{"model":"gemma4-26b-a4b-nvfp4","messages":[{"role":"user","content":"請用一句中文回答：PaulShiaBro vLLM health check OK"}],"max_tokens":64,"temperature":0}'
```

Expected manual result: the second command returns a `chat.completion` response with a concise Chinese health-check answer.

## Acceptance Criteria

- Telegram `/status`, `/dispatch`, `/tmate`, and `/help` behavior remains compatible.
- Telegram non-slash text from an authorized user returns a local vLLM answer.
- Unauthorized users are rejected before any model call.
- Missing or failing vLLM configuration produces sanitized failure text.
- Unit tests run offline.
- Gemini and Copilot provider placeholders are present but inactive.

## Sources

- Gemini API OpenAI compatibility: https://ai.google.dev/gemini-api/docs/openai
- GitHub Copilot CLI authentication: https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli
