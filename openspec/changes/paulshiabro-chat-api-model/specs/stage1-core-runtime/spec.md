## ADDED Requirements

### Requirement: Telegram non-slash chat routing

The Telegram router SHALL route authorized non-slash text messages to a configured chat backend. Text messages whose trimmed content starts with `/` SHALL continue to route through the existing daemon command dispatcher. Unauthorized users MUST be rejected before either command or chat backend execution.

#### Scenario: Authorized non-slash text uses chat backend

- **WHEN** an authorized Telegram user sends `你好`
- **THEN** the router MUST call the configured chat backend with the user id and text
- **THEN** the router MUST return the backend response as the Telegram reply
- **THEN** the daemon command dispatcher MUST NOT be called

#### Scenario: Slash command behavior remains unchanged

- **WHEN** an authorized Telegram user sends `/status`
- **THEN** the router MUST call the existing daemon command path
- **THEN** the chat backend MUST NOT be called

#### Scenario: Unauthorized user cannot chat

- **WHEN** an unauthorized Telegram user sends non-slash text
- **THEN** the router MUST return the existing unauthorized response
- **THEN** neither the daemon command dispatcher nor the chat backend MUST be called

### Requirement: OpenAI-compatible local chat backend

Stage 1 SHALL provide an OpenAI-compatible chat backend for the local vLLM API. The backend MUST read `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` from the environment, call `POST {OPENAI_BASE_URL}/chat/completions`, and extract `choices[0].message.content` as the response text.

#### Scenario: Backend sends chat completion request

- **WHEN** the chat backend is configured with base URL `http://192.168.199.199:8000/v1`, API key `dummy`, and model `gemma4-31b-mtp`
- **THEN** it MUST send a JSON request to `/chat/completions`
- **THEN** the request MUST include the configured model and a user message containing the Telegram text
- **THEN** the request MUST include an Authorization bearer header without exposing the key in logs or errors

#### Scenario: Backend extracts assistant response

- **WHEN** the provider returns a valid chat completion containing `choices[0].message.content`
- **THEN** the backend MUST return that content as the chat reply

#### Scenario: Missing backend configuration fails closed

- **WHEN** any required OpenAI-compatible provider environment variable is absent
- **THEN** Telegram chat MUST return a clear `chat backend 未設定` failure
- **THEN** no HTTP request MUST be attempted

#### Scenario: Provider failure is sanitized

- **WHEN** the provider request times out, returns malformed JSON, or returns a non-success response
- **THEN** Telegram chat MUST return a short sanitized failure message
- **THEN** the response MUST NOT include the API key or full request payload

### Requirement: Future provider placeholders

The project configuration sample SHALL reserve inactive chat provider shapes for Gemini API and GitHub Copilot OAuth. Stage 1 runtime MUST NOT instantiate those providers in this change.

#### Scenario: Reserved providers are documented but inactive

- **WHEN** the sample configuration declares `gemini_api` and `copilot_oauth` chat provider entries with `enabled: false`
- **THEN** loading or documenting the configuration MUST NOT require Gemini or Copilot credentials
- **THEN** runtime chat backend selection MUST instantiate only the OpenAI-compatible provider

### Requirement: Tool bridge remains disabled

The chat integration SHALL NOT allow the model to execute arbitrary tools or shell commands. Any future natural-language-to-command behavior MUST go through an explicit allowlisted bridge and MUST be disabled by default in this change.

#### Scenario: Chat text does not execute tools

- **WHEN** an authorized user sends non-slash text that asks the model to run a command or assign a task
- **THEN** Stage 1 chat MUST treat it as ordinary model conversation
- **THEN** Stage 1 MUST NOT execute `/dispatch`, shell commands, or other tools through the chat backend
