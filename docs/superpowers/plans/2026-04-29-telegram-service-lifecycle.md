# Telegram Service Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real Telegram long-poll listener service for Stage 1, wire it into local startup and deploy templates, and prevent production Telegram `/dispatch` from reporting fake local success.

**Architecture:** Telegram remains a transport adapter: Telegram API updates go to `paulshaclaw.bot.listener`, then to `TelegramCommandRouter`, then to `PaulShiaBroDaemon`. The listener injects a fail-closed coordinator until #14 supplies a real backend. `scripts/start.sh` owns local lifecycle cleanup, while Stage 7 owns deploy template visibility.

**Tech Stack:** Python standard library (`argparse`, `json`, `os`, `time`, `urllib.request`, `unittest`), shell `bash`, existing OpenSpec and deploy planner modules.

---

## File Structure

- Create `tests/test_telegram_listener.py`: offline tests for Telegram API client, listener routing, token/identity checks, and fail-closed dispatch.
- Create `paulshaclaw/bot/listener.py`: Telegram API client, bot settings loader, identity validator, listener loop, fail-closed coordinator, and CLI entrypoint.
- Modify `tests/test_start_sh.py`: fake Python shim learns the Telegram listener module and verifies both monitor and Telegram processes are terminated.
- Modify `scripts/start.sh`: start monitor and Telegram listener in the background, run cockpit in foreground, and terminate background PIDs on exit/signals.
- Modify `tests/test_stage7_deploy_three_plane.py`: require Telegram unit/runtime/secret templates in the template catalog.
- Modify `paulshaclaw/deploy/planner.py`: add Telegram template assets.
- Add `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-telegram.service.tmpl`: deploy unit for Telegram listener.
- Add `paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-telegram.env.tmpl`: runtime env template for Telegram listener.
- Add `paulshaclaw/deploy/templates/secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl`: secret env template for Telegram token and identity checks.
- Modify `docs/ops/recovery.md`: align recovery playbook with actual Telegram unit/log/token checks and fail-closed dispatch behavior.

Implementation note: this workspace may already contain untracked `scripts/start.sh` and `tests/test_start_sh.py` from earlier #13 lifecycle work. Preserve their intent and refine them; do not revert unrelated user files.

---

### Task 1: Telegram API Client And Startup Settings

**Files:**
- Create: `tests/test_telegram_listener.py`
- Create: `paulshaclaw/bot/listener.py`

- [ ] **Step 1: Write the failing API/settings tests**

Create `tests/test_telegram_listener.py` with this initial content:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from paulshaclaw.bot.listener import (
    BotSettings,
    TelegramApiClient,
    TelegramApiError,
    load_bot_settings,
    validate_bot_identity,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        self.requests.append(
            {
                "url": request.full_url,
                "data": request.data or b"",
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("no fake response queued")
        return FakeResponse(self.responses.pop(0))


class TelegramApiClientTests(unittest.TestCase):
    def test_get_me_posts_to_bot_endpoint(self) -> None:
        opener = FakeOpener([{"ok": True, "result": {"id": 42, "username": "psc_bot"}}])
        client = TelegramApiClient("fake-token", opener=opener)

        result = client.get_me()

        self.assertEqual(result["username"], "psc_bot")
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/getMe")
        self.assertEqual(json.loads(opener.requests[0]["data"].decode("utf-8")), {})

    def test_get_updates_sends_offset_and_timeout(self) -> None:
        opener = FakeOpener([{"ok": True, "result": [{"update_id": 11}]}])
        client = TelegramApiClient("fake-token", opener=opener)

        result = client.get_updates(offset=10, timeout=7)

        self.assertEqual(result, [{"update_id": 11}])
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/getUpdates")
        self.assertEqual(json.loads(opener.requests[0]["data"].decode("utf-8")), {"offset": 10, "timeout": 7})

    def test_send_message_posts_chat_id_and_text(self) -> None:
        opener = FakeOpener([{"ok": True, "result": {"message_id": 7}}])
        client = TelegramApiClient("fake-token", opener=opener)

        client.send_message(chat_id=1001, text="PaulShiaBro 狀態")

        body = json.loads(opener.requests[0]["data"].decode("utf-8"))
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/sendMessage")
        self.assertEqual(body, {"chat_id": 1001, "text": "PaulShiaBro 狀態"})

    def test_api_error_raises_without_exposing_token(self) -> None:
        opener = FakeOpener([{"ok": False, "description": "Bad Request"}])
        client = TelegramApiClient("secret-token", opener=opener)

        with self.assertRaisesRegex(TelegramApiError, "Bad Request") as raised:
            client.get_me()

        self.assertNotIn("secret-token", str(raised.exception))


class BotSettingsTests(unittest.TestCase):
    def test_load_bot_settings_requires_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "PSC_TELEGRAM_BOT_TOKEN"):
            load_bot_settings({})

    def test_load_bot_settings_parses_optional_identity(self) -> None:
        settings = load_bot_settings(
            {
                "PSC_TELEGRAM_BOT_TOKEN": "fake-token",
                "PSC_TELEGRAM_EXPECTED_USERNAME": "psc_bot",
                "PSC_TELEGRAM_EXPECTED_BOT_ID": "12345",
            }
        )

        self.assertEqual(settings.token, "fake-token")
        self.assertEqual(settings.expected_username, "psc_bot")
        self.assertEqual(settings.expected_bot_id, 12345)

    def test_validate_bot_identity_rejects_username_mismatch(self) -> None:
        opener = FakeOpener([{"ok": True, "result": {"id": 12345, "username": "other_bot"}}])
        client = TelegramApiClient("fake-token", opener=opener)
        settings = BotSettings(
            token="fake-token",
            expected_username="psc_bot",
            expected_bot_id=12345,
        )

        with self.assertRaisesRegex(ValueError, "username"):
            validate_bot_identity(client, settings, attempts=1, sleep=lambda seconds: None)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the API/settings tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_telegram_listener.TelegramApiClientTests tests.test_telegram_listener.BotSettingsTests -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.bot.listener'`.

- [ ] **Step 3: Implement the minimal API client and startup settings**

Create `paulshaclaw/bot/listener.py` with this content:

```python
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from paulshaclaw.bot.telegram import TelegramCommandRouter
from paulshaclaw.core.config import load_config
from paulshaclaw.core.daemon import PaulShiaBroDaemon


OpenUrl = Callable[[urllib.request.Request, float], Any]


class TelegramApiError(RuntimeError):
    """Raised when Telegram Bot API rejects a request or returns invalid data."""


@dataclass(frozen=True)
class BotSettings:
    token: str
    expected_username: str | None = None
    expected_bot_id: int | None = None


class TelegramApiClient:
    def __init__(
        self,
        token: str,
        *,
        opener: OpenUrl | None = None,
        api_base: str = "https://api.telegram.org",
        timeout: float = 10.0,
    ) -> None:
        self.token = token
        self.opener = opener or urllib.request.urlopen
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def get_me(self) -> dict[str, object]:
        result = self._post("getMe", {})
        if not isinstance(result, dict):
            raise TelegramApiError("Telegram getMe returned non-object result")
        return result

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
        payload: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        result = self._post("getUpdates", payload)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getUpdates returned non-list result")
        updates: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict):
                updates.append(item)
        return updates

    def send_message(self, *, chat_id: int, text: str) -> None:
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def _post(self, method: str, payload: Mapping[str, object]) -> object:
        body = json.dumps(dict(payload)).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}/bot{self.token}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, self.timeout) as response:
                raw = response.read()
        except urllib.error.URLError as error:
            raise TelegramApiError(f"Telegram API request failed: {error.reason}") from error

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TelegramApiError("Telegram API returned invalid JSON") from error

        if not isinstance(decoded, dict):
            raise TelegramApiError("Telegram API returned non-object payload")
        if not decoded.get("ok"):
            description = str(decoded.get("description", "Telegram API request failed"))
            raise TelegramApiError(description)
        return decoded.get("result")


def load_bot_settings(env: Mapping[str, str] | None = None) -> BotSettings:
    resolved_env = os.environ if env is None else env
    token = resolved_env.get("PSC_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("PSC_TELEGRAM_BOT_TOKEN 未設定")

    expected_username = resolved_env.get("PSC_TELEGRAM_EXPECTED_USERNAME", "").strip() or None
    raw_bot_id = resolved_env.get("PSC_TELEGRAM_EXPECTED_BOT_ID", "").strip()
    expected_bot_id = int(raw_bot_id) if raw_bot_id else None
    return BotSettings(
        token=token,
        expected_username=expected_username,
        expected_bot_id=expected_bot_id,
    )


def validate_bot_identity(
    client: TelegramApiClient,
    settings: BotSettings,
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    last_error: TelegramApiError | None = None
    for attempt in range(attempts):
        try:
            identity = client.get_me()
            break
        except TelegramApiError as error:
            last_error = error
            if attempt + 1 >= attempts:
                raise
            sleep(float(attempt + 1))
    else:
        raise TelegramApiError(str(last_error))

    username = str(identity.get("username", ""))
    bot_id = int(identity.get("id", 0))
    if settings.expected_username is not None and username != settings.expected_username:
        raise ValueError(f"Telegram bot username mismatch: expected {settings.expected_username}, got {username}")
    if settings.expected_bot_id is not None and bot_id != settings.expected_bot_id:
        raise ValueError(f"Telegram bot id mismatch: expected {settings.expected_bot_id}, got {bot_id}")
    return identity


class UnavailableCoordinator:
    def create_job(self, *, phase: str, scope: str, payload: dict[str, object]) -> dict[str, object]:
        raise ValueError("coordinator backend 未設定")


class TelegramListener:
    def __init__(
        self,
        *,
        client: TelegramApiClient,
        router: TelegramCommandRouter,
        poll_timeout: int = 30,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.router = router
        self.poll_timeout = poll_timeout
        self.sleep = sleep
        self.offset: int | None = None
        self.max_backoff = 30.0

    def run_once(self) -> None:
        updates = self.client.get_updates(offset=self.offset, timeout=self.poll_timeout)
        for update in updates:
            next_offset = self._next_offset(update)
            try:
                self.process_update(update)
            finally:
                if next_offset is not None:
                    self.offset = next_offset

    def run_forever(self) -> None:
        backoff = 1.0
        while True:
            try:
                self.run_once()
                backoff = 1.0
            except KeyboardInterrupt:
                return
            except TelegramApiError as error:
                print(f"Telegram polling error: {error}", file=sys.stderr)
                self.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    def process_update(self, update: Mapping[str, object]) -> None:
        message = update.get("message")
        if not isinstance(message, Mapping):
            return

        chat = message.get("chat")
        from_user = message.get("from")
        if not isinstance(chat, Mapping) or not isinstance(from_user, Mapping):
            return

        chat_id = chat.get("id")
        user_id = from_user.get("id")
        if not isinstance(chat_id, int) or not isinstance(user_id, int):
            return

        text = message.get("text")
        if not isinstance(text, str):
            self._safe_send(chat_id=chat_id, text="目前只支援文字命令")
            return

        result = self.router.handle_message(user_id=user_id, text=text)
        self._safe_send(chat_id=chat_id, text=str(result["message"]))

    def _safe_send(self, *, chat_id: int, text: str) -> None:
        try:
            self.client.send_message(chat_id=chat_id, text=text)
        except TelegramApiError as error:
            print(f"Telegram sendMessage error: {error}", file=sys.stderr)

    def _next_offset(self, update: Mapping[str, object]) -> int | None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            return update_id + 1
        return None


def build_listener(
    *,
    config_path: str | None,
    settings: BotSettings,
    client: TelegramApiClient | None = None,
    poll_timeout: int = 30,
) -> TelegramListener:
    config = load_config(config_path=config_path)
    daemon = PaulShiaBroDaemon(config=config, coordinator=UnavailableCoordinator())
    router = TelegramCommandRouter(daemon=daemon)
    return TelegramListener(
        client=client or TelegramApiClient(settings.token),
        router=router,
        poll_timeout=poll_timeout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaulShiaBro Telegram listener")
    parser.add_argument("--config", help="Stage 1 JSON 設定檔路徑")
    parser.add_argument("--poll-timeout", type=int, default=30)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_bot_settings()
        client = TelegramApiClient(settings.token)
        validate_bot_identity(client, settings)
        listener = build_listener(
            config_path=args.config,
            settings=settings,
            client=client,
            poll_timeout=args.poll_timeout,
        )
        listener.run_forever()
    except (ValueError, FileNotFoundError, TelegramApiError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the API/settings tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_telegram_listener.TelegramApiClientTests tests.test_telegram_listener.BotSettingsTests -v
```

Expected: PASS for 7 tests.

- [ ] **Step 5: Commit Task 1**

```bash
git add tests/test_telegram_listener.py paulshaclaw/bot/listener.py
git commit -m "feat: add telegram listener api client"
```

---

### Task 2: Listener Routing And Production Dispatch Guard

**Files:**
- Modify: `tests/test_telegram_listener.py`
- Modify: `paulshaclaw/bot/listener.py`

- [ ] **Step 1: Add listener routing and dispatch guard tests**

Append these tests to `tests/test_telegram_listener.py` before the `if __name__ == "__main__":` block:

```python
from paulshaclaw.bot.listener import TelegramListener, UnavailableCoordinator
from paulshaclaw.bot.telegram import TelegramCommandRouter
from paulshaclaw.core.config import load_config
from paulshaclaw.core.daemon import PaulShiaBroDaemon


class FakeTelegramClient:
    def __init__(
        self,
        updates: list[dict[str, object]],
        *,
        send_error: TelegramApiError | None = None,
    ) -> None:
        self.updates = list(updates)
        self.send_error = send_error
        self.sent_messages: list[dict[str, object]] = []
        self.get_updates_calls: list[dict[str, object]] = []

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
        self.get_updates_calls.append({"offset": offset, "timeout": timeout})
        current = self.updates
        self.updates = []
        return current

    def send_message(self, *, chat_id: int, text: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent_messages.append({"chat_id": chat_id, "text": text})


class RecordingRouter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
        self.calls.append({"user_id": user_id, "text": text})
        return {"ok": True, "message": f"reply:{text}"}


def write_stage1_config() -> Path:
    config = {
        "daemon_name": "PaulShiaBro",
        "default_project": "telegram-listener-test",
        "allowed_user_ids": [1001],
        "coordinator": {
            "phase": "build",
            "default_payload": {"source": "telegram-listener-test"},
        },
        "pane_assignments": [],
    }
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(config, handle)
        handle.flush()
    finally:
        handle.close()
    return Path(handle.name)


class TelegramListenerRoutingTests(unittest.TestCase):
    def test_authorized_text_update_routes_through_router_and_replies(self) -> None:
        update = {
            "update_id": 20,
            "message": {
                "chat": {"id": 5001},
                "from": {"id": 1001},
                "text": "/status",
            },
        }
        client = FakeTelegramClient([update])
        router = RecordingRouter()
        listener = TelegramListener(client=client, router=router, poll_timeout=5)

        listener.run_once()

        self.assertEqual(router.calls, [{"user_id": 1001, "text": "/status"}])
        self.assertEqual(client.sent_messages, [{"chat_id": 5001, "text": "reply:/status"}])
        self.assertEqual(listener.offset, 21)
        self.assertEqual(client.get_updates_calls[0]["timeout"], 5)

    def test_non_text_update_replies_without_routing(self) -> None:
        update = {
            "update_id": 21,
            "message": {
                "chat": {"id": 5001},
                "from": {"id": 1001},
                "photo": [{"file_id": "photo-1"}],
            },
        }
        client = FakeTelegramClient([update])
        router = RecordingRouter()
        listener = TelegramListener(client=client, router=router)

        listener.run_once()

        self.assertEqual(router.calls, [])
        self.assertEqual(client.sent_messages, [{"chat_id": 5001, "text": "目前只支援文字命令"}])
        self.assertEqual(listener.offset, 22)

    def test_send_failure_does_not_rerun_router(self) -> None:
        update = {
            "update_id": 22,
            "message": {
                "chat": {"id": 5001},
                "from": {"id": 1001},
                "text": "/status",
            },
        }
        client = FakeTelegramClient([update], send_error=TelegramApiError("send failed"))
        router = RecordingRouter()
        listener = TelegramListener(client=client, router=router)

        listener.run_once()

        self.assertEqual(router.calls, [{"user_id": 1001, "text": "/status"}])
        self.assertEqual(listener.offset, 23)

    def test_dispatch_without_backend_fails_closed(self) -> None:
        config_path = write_stage1_config()
        self.addCleanup(config_path.unlink, missing_ok=True)
        config = load_config(config_path=config_path)
        daemon = PaulShiaBroDaemon(config=config, coordinator=UnavailableCoordinator())
        router = TelegramCommandRouter(daemon=daemon)
        client = FakeTelegramClient(
            [
                {
                    "update_id": 23,
                    "message": {
                        "chat": {"id": 5001},
                        "from": {"id": 1001},
                        "text": "/dispatch sample-task",
                    },
                }
            ]
        )
        listener = TelegramListener(client=client, router=router)

        listener.run_once()

        self.assertEqual(client.sent_messages[0]["chat_id"], 5001)
        self.assertIn("coordinator backend 未設定", client.sent_messages[0]["text"])
        self.assertNotIn("local-", client.sent_messages[0]["text"])
```

- [ ] **Step 2: Run the listener routing tests to verify they fail for any missing behavior**

Run:

```bash
python3 -m unittest tests.test_telegram_listener.TelegramListenerRoutingTests -v
```

Expected before Task 1 implementation is complete: FAIL with missing listener symbols. Expected after Task 1 implementation: PASS. If any case fails, keep the failure output and adjust only `paulshaclaw/bot/listener.py`.

- [ ] **Step 3: Run all Telegram listener tests**

Run:

```bash
python3 -m unittest tests.test_telegram_listener -v
```

Expected: PASS for 11 tests.

- [ ] **Step 4: Commit Task 2**

```bash
git add tests/test_telegram_listener.py paulshaclaw/bot/listener.py
git commit -m "feat: route telegram updates through daemon"
```

---

### Task 3: Local Startup Lifecycle

**Files:**
- Modify: `tests/test_start_sh.py`
- Modify: `scripts/start.sh`

- [ ] **Step 1: Extend the fake Python shim**

In `tests/test_start_sh.py`, replace the existing `FAKE_PYTHON` value with this version:

```python
FAKE_PYTHON = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    from __future__ import annotations

    import os
    import signal
    import sys
    from pathlib import Path


    def _module_name(argv: list[str]) -> str | None:
        if len(argv) >= 3 and argv[1] == "-m":
            return argv[2]
        return None


    def _write_pid(env_name: str) -> None:
        pidfile = Path(os.environ[env_name])
        pidfile.write_text(str(os.getpid()), encoding="utf-8")


    def _wait_forever() -> int:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.pause()
        return 0


    def main() -> int:
        module = _module_name(sys.argv)
        if module == "paulshaclaw.monitor":
            _write_pid("FAKE_MONITOR_PIDFILE")
            return _wait_forever()

        if module == "paulshaclaw.bot.listener":
            _write_pid("FAKE_TELEGRAM_PIDFILE")
            return _wait_forever()

        if module == "paulshaclaw.cockpit":
            signal.pause()
            return 0

        print(f"unexpected argv: {sys.argv!r}", file=sys.stderr)
        return 2


    if __name__ == "__main__":
        raise SystemExit(main())
    """
)
```

- [ ] **Step 2: Replace the lifecycle test with monitor plus Telegram assertions**

Replace `test_monitor_is_terminated_when_cockpit_receives_sigint` with:

```python
    def test_background_services_are_terminated_when_cockpit_receives_sigint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_root = tmpdir_path / "repo"
            home_dir = tmpdir_path / "home"
            fake_bin = repo_root / ".venv" / "bin"
            fake_scripts = repo_root / "scripts"
            monitor_pidfile = tmpdir_path / "monitor.pid"
            telegram_pidfile = tmpdir_path / "telegram.pid"

            fake_bin.mkdir(parents=True)
            fake_scripts.mkdir(parents=True)
            home_dir.mkdir(parents=True)

            fake_python = fake_bin / "python"
            fake_python.write_text(FAKE_PYTHON, encoding="utf-8")
            fake_python.chmod(0o755)

            start_sh = fake_scripts / "start.sh"
            start_sh_text = START_SH.read_text(encoding="utf-8").replace(
                "REPO=/home/paul_chen/prj_pri/paulshaclaw",
                f"REPO={repo_root}",
            )
            start_sh.write_text(start_sh_text, encoding="utf-8")
            start_sh.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(home_dir)
            env["TMUX_PANE"] = "%0"
            env["FAKE_MONITOR_PIDFILE"] = str(monitor_pidfile)
            env["FAKE_TELEGRAM_PIDFILE"] = str(telegram_pidfile)

            proc = subprocess.Popen(
                ["bash", str(start_sh)],
                cwd=repo_root,
                env=env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                self._wait_for_file(monitor_pidfile)
                self._wait_for_file(telegram_pidfile)
                monitor_pid = int(monitor_pidfile.read_text(encoding="utf-8").strip())
                telegram_pid = int(telegram_pidfile.read_text(encoding="utf-8").strip())

                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                proc.wait(timeout=10)

                with self.assertRaises(ProcessLookupError):
                    os.kill(monitor_pid, 0)
                with self.assertRaises(ProcessLookupError):
                    os.kill(telegram_pid, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                for pidfile in (monitor_pidfile, telegram_pidfile):
                    if pidfile.exists():
                        try:
                            os.kill(int(pidfile.read_text(encoding="utf-8").strip()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
```

- [ ] **Step 3: Run the start script test to verify it fails before script update**

Run:

```bash
python3 -m unittest tests.test_start_sh -v
```

Expected: FAIL waiting for `telegram.pid`, because `scripts/start.sh` has not started `paulshaclaw.bot.listener` yet.

- [ ] **Step 4: Replace `scripts/start.sh` with explicit PID cleanup**

Set `scripts/start.sh` to:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO=/home/paul_chen/prj_pri/paulshaclaw
PY=$REPO/.venv/bin/python
LOG_DIR=${HOME}/.agents/log

mkdir -p "$LOG_DIR"

pids=()

start_background() {
  local name=$1
  local logfile=$2
  shift 2

  "$@" >> "$logfile" 2>&1 &
  local pid=$!
  pids+=("$pid")
  echo "$name pid=$pid"
}

cleanup() {
  local pid
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

start_background monitor "$LOG_DIR/monitor.log" "$PY" -m paulshaclaw.monitor
start_background telegram "$LOG_DIR/telegram.log" "$PY" -m paulshaclaw.bot.listener

set +e
"$PY" -m paulshaclaw.cockpit --cockpit-pane "${TMUX_PANE:?must run inside tmux}"
status=$?
set -e

exit "$status"
```

- [ ] **Step 5: Run start script checks**

Run:

```bash
bash -n scripts/start.sh
python3 -m unittest tests.test_start_sh -v
```

Expected: shell syntax check exits 0; unittest PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add scripts/start.sh tests/test_start_sh.py
git commit -m "feat: run telegram listener with start script"
```

---

### Task 4: Stage 7 Deploy Templates

**Files:**
- Modify: `tests/test_stage7_deploy_three_plane.py`
- Modify: `paulshaclaw/deploy/planner.py`
- Add: `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-telegram.service.tmpl`
- Add: `paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-telegram.env.tmpl`
- Add: `paulshaclaw/deploy/templates/secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl`

- [ ] **Step 1: Strengthen Stage 7 template tests**

In `tests/test_stage7_deploy_three_plane.py`, replace `TemplateMappingTests.test_template_assets_cover_three_planes` with:

```python
    def test_template_assets_cover_three_planes(self) -> None:
        assets = list_template_assets()
        target_paths = {asset.target_path for asset in assets}

        self.assertGreaterEqual(len(assets), 7)
        self.assertEqual({asset.plane for asset in assets}, {"core", "state", "secret"})
        self.assertIn("core/systemd/paulshaclaw.service", target_paths)
        self.assertIn("core/systemd/paulshaclaw-telegram.service", target_paths)
        self.assertIn("core/runtime/paulshaclaw.env", target_paths)
        self.assertIn("core/runtime/paulshaclaw-telegram.env", target_paths)
        self.assertIn("secret/bootstrap/paulshaclaw.telegram.secret.env", target_paths)
        for asset in assets:
            self.assertTrue(asset.template_path.exists(), msg=str(asset.template_path))
            self.assertTrue(asset.target_path.endswith(asset.expected_suffix))
```

Add this test to `TemplateMappingTests`:

```python
    def test_telegram_unit_rename_rule(self) -> None:
        target = resolve_template_target(
            "core/systemd/__INSTANCE__-telegram.service.tmpl",
            instance_name="demo-agent",
        )

        self.assertEqual(target, "core/systemd/demo-agent-telegram.service")
```

- [ ] **Step 2: Run Stage 7 tests to verify they fail before templates exist**

Run:

```bash
python3 -m unittest tests.test_stage7_deploy_three_plane.TemplateMappingTests -v
```

Expected: FAIL because Telegram template assets are not in `_TEMPLATE_CATALOG`.

- [ ] **Step 3: Add template catalog entries**

In `paulshaclaw/deploy/planner.py`, update `_TEMPLATE_CATALOG` to:

```python
_TEMPLATE_CATALOG = (
    (
        "core",
        "core/systemd/__INSTANCE__.service.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "core",
        "core/systemd/__INSTANCE__-telegram.service.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "core",
        "core/runtime/__INSTANCE__.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "core",
        "core/runtime/__INSTANCE__-telegram.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "state",
        "state/config/__INSTANCE__.state.json.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "secret",
        "secret/bootstrap/__INSTANCE__.secret.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "secret",
        "secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
)
```

- [ ] **Step 4: Add Telegram deploy templates**

Create `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-telegram.service.tmpl`:

```ini
[Unit]
Description=__INSTANCE__ Telegram listener
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__.env
EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__-telegram.env
EnvironmentFile=%h/.config/paulshaclaw/__INSTANCE__.telegram.secret.env
ExecStart=/usr/bin/env python3 -m paulshaclaw.bot.listener
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Create `paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-telegram.env.tmpl`:

```dotenv
PSC_INSTANCE=__INSTANCE__
PSC_PLANE=core
PSC_TELEGRAM_POLL_TIMEOUT=30
```

Create `paulshaclaw/deploy/templates/secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl`:

```dotenv
PSC_TELEGRAM_BOT_TOKEN=replace-with-botfather-token
PSC_TELEGRAM_EXPECTED_USERNAME=
PSC_TELEGRAM_EXPECTED_BOT_ID=
```

- [ ] **Step 5: Run Stage 7 tests**

Run:

```bash
python3 -m unittest tests.test_stage7_deploy_three_plane -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add tests/test_stage7_deploy_three_plane.py paulshaclaw/deploy/planner.py paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-telegram.service.tmpl paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-telegram.env.tmpl paulshaclaw/deploy/templates/secret/bootstrap/__INSTANCE__.telegram.secret.env.tmpl
git commit -m "feat: add telegram deploy templates"
```

---

### Task 5: Recovery Docs And Focused Verification

**Files:**
- Modify: `docs/ops/recovery.md`

- [ ] **Step 1: Update full runtime restart playbook service names**

In `docs/ops/recovery.md`, replace the full runtime restart service collection commands with:

```markdown
1. 先收集三個服務狀態：
   - `systemctl --user status paulshaclaw.service`
   - `systemctl --user status paulshaclaw-telegram.service`
   - `systemctl --user status paulshaclaw-janitor.service`
```

Replace the restart ordering sentence with:

```markdown
4. 依序啟動 daemon -> Telegram listener -> janitor。Telegram listener 的 raw log 位置為 `~/.agents/log/telegram.log`；若由 systemd 啟動，另查 `journalctl --user -u paulshaclaw-telegram.service`。
```

- [ ] **Step 2: Add Telegram listener recovery checks**

Add this section before `## Playbook: memory pipeline 阻塞`:

```markdown
## Playbook: Telegram listener 未接上

### 觸發條件

- Operator 對 bot 發 `/status` 無回覆。
- `~/.agents/log/telegram.log` 顯示 token、config、getMe 或 polling 錯誤。
- `systemctl --user status paulshaclaw-telegram.service` 顯示 crash loop。

### 復原步驟

1. 檢查 secret env 是否存在且權限只允許 owner：
   - `ls -l ~/.config/paulshaclaw/paulshaclaw.telegram.secret.env`
2. 確認必要環境值：
   - `PSC_TELEGRAM_BOT_TOKEN`
   - `PSC_STAGE1_CONFIG`
   - 可選：`PSC_TELEGRAM_EXPECTED_USERNAME`、`PSC_TELEGRAM_EXPECTED_BOT_ID`
3. 檢查 bot identity：
   - listener 啟動會呼叫 `getMe`；若 expected username / bot id 不符，會 fail-close。
4. 確認 `allowed_user_ids` 放的是人類 Telegram user id，不是 bot id。
5. 重啟 Telegram listener：
   - local integrated mode：重新執行 `scripts/start.sh`
   - systemd mode：`systemctl --user restart paulshaclaw-telegram.service`
6. 驗證：
   - 授權 user 發 `/status` 會收到狀態
   - 未授權 user 發 `/status` 會收到 `未授權使用者`
   - #14 完成前，`/dispatch sample-task` 回覆 `coordinator backend 未設定`，不得回 `local-*` job id
```

- [ ] **Step 3: Run focused verification**

Run:

```bash
python3 -m unittest tests.test_telegram_listener tests.test_start_sh tests.test_stage7_deploy_three_plane -v
```

Expected: PASS.

- [ ] **Step 4: Run broad verification**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS where tmux is available. If `tests.test_stage11_operator_cockpit_e2e` fails with `error connecting to /tmp/tmux-1000/default (Operation not permitted)`, record it as an environment-only tmux restriction and include the focused passing command in the final report.

- [ ] **Step 5: Commit Task 5**

```bash
git add docs/ops/recovery.md
git commit -m "docs: document telegram listener recovery"
```

---

### Task 6: Final OpenSpec And Worktree Check

**Files:**
- Verify: `openspec/changes/stage1-telegram-service-lifecycle/`
- Verify: all files touched by Tasks 1-5

- [ ] **Step 1: Validate OpenSpec status**

Run:

```bash
openspec status --change stage1-telegram-service-lifecycle
```

Expected:

```text
Change: stage1-telegram-service-lifecycle
Schema: spec-driven
Progress: 4/4 artifacts complete

[x] proposal
[x] design
[x] specs
[x] tasks

All artifacts complete!
```

PostHog network flush errors after this output are telemetry noise if the command exits 0 and the status shows all artifacts complete.

- [ ] **Step 2: Inspect worktree status**

Run:

```bash
git status --short --branch
```

Expected: only intentional OpenSpec/plan artifacts and pre-existing unrelated untracked paths remain. No generated cache files should be staged.

- [ ] **Step 3: Final implementation summary**

Report:

```text
Implemented #13 Telegram service lifecycle.

Verification:
- python3 -m unittest tests.test_telegram_listener tests.test_start_sh tests.test_stage7_deploy_three_plane -v
- python3 -m unittest discover -s tests -v

Known follow-up:
- #14 defines the real coordinator adapter. Until then, Telegram /dispatch fails closed with coordinator backend 未設定.
```

## Self-Review

- Spec coverage: Tasks 1-2 cover listener, token checks, routing, and dispatch guard; Task 3 covers local lifecycle; Task 4 covers Stage 7 deploy templates; Task 5 covers recovery docs and verification.
- Placeholder scan: no task depends on unspecified files, unnamed functions, or future decisions outside #14.
- Type consistency: `TelegramApiClient`, `TelegramListener`, `BotSettings`, `UnavailableCoordinator`, and `TelegramApiError` are introduced before later tasks reference them.
