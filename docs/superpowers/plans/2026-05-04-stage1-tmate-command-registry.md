# Stage1 Tmate Command Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a registry-backed Stage 1 command surface with Telegram command-menu sync, generated `/help`, safe shell `func_call`, and managed `/tmate` lifecycle with 3600-second no-client idle stop.

**Architecture:** `commands.json` becomes the single source for Stage 1 runtime command metadata. `PaulShiaBroDaemon` delegates command lookup/execution to focused registry and dispatcher modules, while Telegram startup syncs `telegram_menu` entries through `setMyCommands`; tmate state is managed under `~/.agents/`.

**Tech Stack:** Python standard library, `unittest`, Telegram Bot API client already in `paulshaclaw.bot.listener`, tmate CLI invoked through injectable argv executor.

---

## File Structure

- Create `paulshaclaw/core/commands.json`: tracked command registry for `/help`, `/status`, `/dispatch`, and `/tmate`.
- Create `paulshaclaw/core/command_registry.py`: JSON loading, data classes, registry invariants, Telegram command derivation, help rendering.
- Create `paulshaclaw/core/command_dispatcher.py`: parse slash commands, call Python handlers, execute safe shell argv entries.
- Create `paulshaclaw/core/tmate.py`: managed tmate session state, fixed argv calls, link readout, idle cleanup.
- Modify `paulshaclaw/core/daemon.py`: wire registry, dispatcher, existing status/dispatch handlers, tmate handler, cleanup hook.
- Modify `paulshaclaw/bot/telegram.py`: format generated help and tmate responses.
- Modify `paulshaclaw/bot/listener.py`: add `setMyCommands`, startup sync, cleanup callback, outbound redaction.
- Create `tests/test_stage1_command_registry.py`: registry, help, dispatcher, and shell argv tests.
- Create `tests/test_stage1_tmate.py`: fake-executor tests for tmate lifecycle and idle cleanup.
- Modify `tests/test_stage1_smoke.py`: add `/help` smoke coverage and keep `/status`/`/dispatch` behavior stable.
- Modify `tests/test_telegram_listener.py`: add `setMyCommands`, startup ordering, cleanup loop, and redaction tests.

## Task 1: Command Registry Loader

**Files:**
- Create: `paulshaclaw/core/commands.json`
- Create: `paulshaclaw/core/command_registry.py`
- Test: `tests/test_stage1_command_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_stage1_command_registry.py` with this initial content:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paulshaclaw.core.command_registry import (
    CommandRegistryError,
    load_command_registry,
    load_default_command_registry,
)


class CommandRegistryTests(unittest.TestCase):
    def write_registry(self, payload: dict[str, object]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        try:
            json.dump(payload, handle)
            handle.flush()
        finally:
            handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_default_registry_lists_stage1_commands(self) -> None:
        registry = load_default_command_registry()

        self.assertEqual(
            [command.name for command in registry.commands],
            ["/help", "/status", "/dispatch", "/tmate"],
        )
        self.assertEqual(
            registry.telegram_commands(),
            [
                {"command": "help", "description": "列出可用命令"},
                {"command": "status", "description": "顯示 runtime 狀態"},
                {"command": "dispatch", "description": "派工或送訊息到 pane"},
                {"command": "tmate", "description": "管理 tmate remote access"},
            ],
        )

    def test_rejects_duplicate_command_names(self) -> None:
        path = self.write_registry(
            {
                "version": 1,
                "commands": [
                    {
                        "name": "/help",
                        "usage": "/help",
                        "summary": "help",
                        "telegram_menu": {"enabled": True, "command": "help", "description": "help"},
                        "func_call": {"type": "python", "target": "help"},
                    },
                    {
                        "name": "/help",
                        "usage": "/help",
                        "summary": "help again",
                        "telegram_menu": {"enabled": False},
                        "func_call": {"type": "python", "target": "help"},
                    },
                ],
            }
        )

        with self.assertRaisesRegex(CommandRegistryError, "duplicate command"):
            load_command_registry(path)

    def test_rejects_invalid_telegram_menu_command(self) -> None:
        path = self.write_registry(
            {
                "version": 1,
                "commands": [
                    {
                        "name": "/bad",
                        "usage": "/bad",
                        "summary": "bad",
                        "telegram_menu": {"enabled": True, "command": "/bad", "description": "bad"},
                        "func_call": {"type": "python", "target": "help"},
                    }
                ],
            }
        )

        with self.assertRaisesRegex(CommandRegistryError, "telegram_menu.command"):
            load_command_registry(path)

    def test_rejects_unknown_shell_placeholder(self) -> None:
        path = self.write_registry(
            {
                "version": 1,
                "commands": [
                    {
                        "name": "/bad",
                        "usage": "/bad",
                        "summary": "bad",
                        "telegram_menu": {"enabled": False},
                        "func_call": {"type": "shell", "argv": ["printf", "{unsafe}"]},
                    }
                ],
            }
        )

        with self.assertRaisesRegex(CommandRegistryError, "unsupported placeholder"):
            load_command_registry(path)

    def test_render_help_uses_registry_metadata(self) -> None:
        registry = load_default_command_registry()

        help_text = registry.render_help()
        tmate_text = registry.render_help("/tmate")
        slashless_text = registry.render_help("tmate")

        self.assertIn("/help [command] - 列出可用命令，或顯示單一命令用法", help_text)
        self.assertIn("/tmate [status|start|stop]", tmate_text)
        self.assertEqual(tmate_text, slashless_text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run registry tests to verify they fail**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_command_registry -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.core.command_registry'`.

- [ ] **Step 3: Create default command registry JSON**

Create `paulshaclaw/core/commands.json`:

```json
{
  "version": 1,
  "defaults": {
    "timeout_seconds": 30
  },
  "commands": [
    {
      "name": "/help",
      "usage": "/help [command]",
      "summary": "列出可用命令，或顯示單一命令用法",
      "telegram_menu": {
        "enabled": true,
        "command": "help",
        "description": "列出可用命令"
      },
      "func_call": {
        "type": "python",
        "target": "help"
      }
    },
    {
      "name": "/status",
      "usage": "/status",
      "summary": "顯示 PaulShiaBro runtime 狀態",
      "telegram_menu": {
        "enabled": true,
        "command": "status",
        "description": "顯示 runtime 狀態"
      },
      "func_call": {
        "type": "python",
        "target": "status"
      }
    },
    {
      "name": "/dispatch",
      "usage": "/dispatch <task_id>|<pane_id> <message>",
      "summary": "派工到 coordinator，或送訊息到 tmux pane",
      "telegram_menu": {
        "enabled": true,
        "command": "dispatch",
        "description": "派工或送訊息到 pane"
      },
      "func_call": {
        "type": "python",
        "target": "dispatch"
      }
    },
    {
      "name": "/tmate",
      "usage": "/tmate [status|start|stop]",
      "summary": "管理 tmate remote access session",
      "telegram_menu": {
        "enabled": true,
        "command": "tmate",
        "description": "管理 tmate remote access"
      },
      "func_call": {
        "type": "python",
        "target": "tmate",
        "timeout_seconds": 3600
      }
    }
  ]
}
```

- [ ] **Step 4: Implement registry loader**

Create `paulshaclaw/core/command_registry.py`:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


TELEGRAM_COMMAND_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class CommandRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramMenu:
    enabled: bool
    command: str = ""
    description: str = ""


@dataclass(frozen=True)
class FuncCall:
    type: str
    target: str = ""
    argv: tuple[str, ...] = ()
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class CommandSpec:
    name: str
    usage: str
    summary: str
    telegram_menu: TelegramMenu
    func_call: FuncCall


@dataclass(frozen=True)
class CommandRegistry:
    commands: tuple[CommandSpec, ...]
    default_timeout_seconds: int = 30

    def get(self, name: str) -> CommandSpec:
        normalized = name if name.startswith("/") else f"/{name}"
        for command in self.commands:
            if command.name == normalized:
                return command
        raise CommandRegistryError(f"unknown command: {name}")

    def telegram_commands(self) -> list[dict[str, str]]:
        return [
            {
                "command": command.telegram_menu.command,
                "description": command.telegram_menu.description,
            }
            for command in self.commands
            if command.telegram_menu.enabled
        ]

    def render_help(self, command_name: str | None = None) -> str:
        if command_name:
            command = self.get(command_name)
            return "\n".join([command.usage, command.summary])
        lines = ["可用命令:"]
        for command in self.commands:
            lines.append(f"{command.usage} - {command.summary}")
        return "\n".join(lines)


def load_default_command_registry() -> CommandRegistry:
    return load_command_registry(Path(__file__).with_name("commands.json"))


def load_command_registry(path: str | Path) -> CommandRegistry:
    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise CommandRegistryError("registry must be a JSON object")
    return parse_command_registry(payload)


def parse_command_registry(payload: Mapping[str, object]) -> CommandRegistry:
    if payload.get("version") != 1:
        raise CommandRegistryError("registry version must be 1")

    defaults = payload.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, Mapping):
        raise CommandRegistryError("defaults must be an object")
    default_timeout = int(defaults.get("timeout_seconds", 30))

    raw_commands = payload.get("commands")
    if not isinstance(raw_commands, list) or not raw_commands:
        raise CommandRegistryError("commands must be a non-empty list")

    commands: list[CommandSpec] = []
    seen: set[str] = set()
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, Mapping):
            raise CommandRegistryError(f"commands[{index}] must be an object")
        command = _parse_command(raw_command, index=index)
        if command.name in seen:
            raise CommandRegistryError(f"duplicate command: {command.name}")
        seen.add(command.name)
        commands.append(command)

    return CommandRegistry(commands=tuple(commands), default_timeout_seconds=default_timeout)


def _parse_command(payload: Mapping[str, object], *, index: int) -> CommandSpec:
    name = _required_str(payload, "name", index=index)
    if not name.startswith("/"):
        raise CommandRegistryError(f"commands[{index}].name must start with /")
    usage = _required_str(payload, "usage", index=index)
    summary = _required_str(payload, "summary", index=index)

    raw_menu = payload.get("telegram_menu")
    if not isinstance(raw_menu, Mapping):
        raise CommandRegistryError(f"commands[{index}].telegram_menu must be an object")
    menu = _parse_telegram_menu(raw_menu, index=index)

    raw_call = payload.get("func_call")
    if not isinstance(raw_call, Mapping):
        raise CommandRegistryError(f"commands[{index}].func_call must be an object")
    func_call = _parse_func_call(raw_call, index=index)

    return CommandSpec(
        name=name,
        usage=usage,
        summary=summary,
        telegram_menu=menu,
        func_call=func_call,
    )


def _parse_telegram_menu(payload: Mapping[str, object], *, index: int) -> TelegramMenu:
    enabled = bool(payload.get("enabled", False))
    command = str(payload.get("command", ""))
    description = str(payload.get("description", ""))
    if enabled:
        if not TELEGRAM_COMMAND_RE.match(command):
            raise CommandRegistryError(f"commands[{index}].telegram_menu.command is invalid")
        if not 1 <= len(description) <= 256:
            raise CommandRegistryError(f"commands[{index}].telegram_menu.description is invalid")
    return TelegramMenu(enabled=enabled, command=command, description=description)


def _parse_func_call(payload: Mapping[str, object], *, index: int) -> FuncCall:
    call_type = str(payload.get("type", ""))
    raw_timeout = payload.get("timeout_seconds")
    timeout = int(raw_timeout) if raw_timeout is not None else None
    if call_type == "python":
        target = str(payload.get("target", ""))
        if not target:
            raise CommandRegistryError(f"commands[{index}].func_call.target is required")
        return FuncCall(type=call_type, target=target, timeout_seconds=timeout)
    if call_type == "shell":
        raw_argv = payload.get("argv")
        if not isinstance(raw_argv, list) or not raw_argv:
            raise CommandRegistryError(f"commands[{index}].func_call.argv must be a non-empty list")
        argv = tuple(str(item) for item in raw_argv)
        _validate_shell_argv(argv, index=index)
        return FuncCall(type=call_type, argv=argv, timeout_seconds=timeout)
    raise CommandRegistryError(f"commands[{index}].func_call.type is unsupported: {call_type}")


def _validate_shell_argv(argv: tuple[str, ...], *, index: int) -> None:
    for value in argv:
        for match in PLACEHOLDER_RE.findall(value):
            if match == "args":
                continue
            if match.startswith("arg") and match[3:].isdigit():
                continue
            raise CommandRegistryError(f"commands[{index}] unsupported placeholder: {{{match}}}")


def _required_str(payload: Mapping[str, object], key: str, *, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CommandRegistryError(f"commands[{index}].{key} is required")
    return value
```

- [ ] **Step 5: Run registry tests to verify they pass**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_command_registry -v
```

Expected: PASS for the registry tests.

- [ ] **Step 6: Commit registry foundation**

```bash
git add paulshaclaw/core/commands.json paulshaclaw/core/command_registry.py tests/test_stage1_command_registry.py
git commit -m "feat(stage1): add runtime command registry"
```

## Task 2: Dispatcher And Daemon Routing

**Files:**
- Create: `paulshaclaw/core/command_dispatcher.py`
- Modify: `paulshaclaw/core/daemon.py`
- Modify: `paulshaclaw/bot/telegram.py`
- Modify: `tests/test_stage1_command_registry.py`
- Modify: `tests/test_stage1_smoke.py`

- [ ] **Step 1: Add failing dispatcher tests**

Append these tests to `tests/test_stage1_command_registry.py` before `if __name__ == "__main__":`:

```python

class CommandDispatcherTests(unittest.TestCase):
    def test_dispatcher_runs_python_handler(self) -> None:
        from paulshaclaw.core.command_dispatcher import CommandDispatcher

        registry = load_default_command_registry()
        dispatcher = CommandDispatcher(
            registry,
            python_handlers={
                "help": lambda args, command: {"ok": True, "text": registry.render_help(args[0] if args else None)},
                "status": lambda args, command: {"ok": True, "kind": "status", "args": args},
                "dispatch": lambda args, command: {"ok": True, "kind": "dispatch", "args": args},
                "tmate": lambda args, command: {"ok": True, "kind": "tmate", "args": args},
            },
        )

        result = dispatcher.execute("/status")

        self.assertEqual(result, {"ok": True, "kind": "status", "args": []})

    def test_dispatcher_runs_shell_argv_without_shell(self) -> None:
        from paulshaclaw.core.command_dispatcher import CommandDispatcher
        from paulshaclaw.core.command_registry import parse_command_registry

        calls: list[dict[str, object]] = []

        def fake_executor(argv: list[str], timeout: int) -> str:
            calls.append({"argv": argv, "timeout": timeout})
            return "hello"

        registry = parse_command_registry(
            {
                "version": 1,
                "defaults": {"timeout_seconds": 30},
                "commands": [
                    {
                        "name": "/echo",
                        "usage": "/echo <word>",
                        "summary": "echo",
                        "telegram_menu": {"enabled": False},
                        "func_call": {"type": "shell", "argv": ["printf", "{arg0}"], "timeout_seconds": 9},
                    }
                ],
            }
        )
        dispatcher = CommandDispatcher(registry, python_handlers={}, shell_executor=fake_executor)

        result = dispatcher.execute("/echo hello")

        self.assertEqual(result, {"ok": True, "kind": "shell", "stdout": "hello"})
        self.assertEqual(calls, [{"argv": ["printf", "hello"], "timeout": 9}])

    def test_dispatcher_rejects_unknown_command(self) -> None:
        from paulshaclaw.core.command_dispatcher import CommandDispatcher

        dispatcher = CommandDispatcher(load_default_command_registry(), python_handlers={})

        with self.assertRaisesRegex(ValueError, "不支援的指令"):
            dispatcher.execute("/missing")
```

Append this smoke test to `Stage1SmokeTest` in `tests/test_stage1_smoke.py`:

```python
    def test_help_command_lists_runtime_commands(self) -> None:
        config_path = self.make_config_path()
        daemon = PaulShiaBroDaemon(config=load_config(config_path=config_path), coordinator=FakeCoordinator())
        router = TelegramCommandRouter(daemon=daemon)

        result = router.handle_message(user_id=1001, text="/help")

        self.assertTrue(result["ok"])
        self.assertIn("/tmate [status|start|stop]", result["message"])
        self.assertIn("/dispatch <task_id>|<pane_id> <message>", result["message"])
```

- [ ] **Step 2: Run dispatcher tests to verify they fail**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_command_registry tests.test_stage1_smoke.Stage1SmokeTest.test_help_command_lists_runtime_commands -v
```

Expected: FAIL with `ModuleNotFoundError` for `paulshaclaw.core.command_dispatcher` or unsupported `/help`.

- [ ] **Step 3: Implement dispatcher module**

Create `paulshaclaw/core/command_dispatcher.py`:

```python
from __future__ import annotations

import subprocess
from typing import Callable

from paulshaclaw.core.command_registry import CommandRegistry, CommandSpec


PythonHandler = Callable[[list[str], CommandSpec], dict[str, object]]
ShellExecutor = Callable[[list[str], int], str]


class CommandDispatcher:
    def __init__(
        self,
        registry: CommandRegistry,
        *,
        python_handlers: dict[str, PythonHandler],
        shell_executor: ShellExecutor | None = None,
    ) -> None:
        self.registry = registry
        self.python_handlers = dict(python_handlers)
        self.shell_executor = shell_executor or default_shell_executor

    def execute(self, command_text: str) -> dict[str, object]:
        normalized = command_text.strip()
        if not normalized:
            raise ValueError("不支援的指令: ")
        parts = normalized.split()
        command_name = parts[0]
        args = parts[1:]
        try:
            command = self.registry.get(command_name)
        except ValueError as error:
            raise ValueError(f"不支援的指令: {command_text}") from error

        if command.func_call.type == "python":
            handler = self.python_handlers.get(command.func_call.target)
            if handler is None:
                raise ValueError(f"不支援的指令: {command_text}")
            return handler(args, command)

        if command.func_call.type == "shell":
            timeout = command.func_call.timeout_seconds or self.registry.default_timeout_seconds
            argv = expand_shell_argv(command.func_call.argv, args)
            stdout = self.shell_executor(argv, timeout)
            return {"ok": True, "kind": "shell", "stdout": stdout}

        raise ValueError(f"不支援的指令: {command_text}")


def expand_shell_argv(argv: tuple[str, ...], args: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in argv:
        item = value.replace("{args}", " ".join(args))
        for index, arg in enumerate(args):
            item = item.replace(f"{{arg{index}}}", arg)
        if "{arg" in item:
            raise ValueError("shell command argument missing")
        expanded.append(item)
    return expanded


def default_shell_executor(argv: list[str], timeout: int) -> str:
    try:
        completed = subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"shell command timed out after {timeout}s") from error
    except FileNotFoundError as error:
        raise ValueError(f"command not found: {argv[0]}") from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        message = stderr if stderr else f"command failed with exit code {error.returncode}"
        raise ValueError(message) from error
    return completed.stdout.strip()
```

- [ ] **Step 4: Route daemon through dispatcher**

Modify `paulshaclaw/core/daemon.py`:

Add imports:

```python
from paulshaclaw.core.command_dispatcher import CommandDispatcher
from paulshaclaw.core.command_registry import CommandRegistry, CommandSpec, load_default_command_registry
```

Change `PaulShiaBroDaemon.__init__` and add handler methods:

```python
class PaulShiaBroDaemon:
    def __init__(
        self,
        config: AppConfig,
        coordinator: CoordinatorClient | None = None,
        command_registry: CommandRegistry | None = None,
    ) -> None:
        self.config = config
        self.coordinator = coordinator or LocalCoordinator()
        self.command_registry = command_registry or load_default_command_registry()
        self.command_dispatcher = CommandDispatcher(
            self.command_registry,
            python_handlers={
                "help": self._handle_help_command,
                "status": self._handle_status_command,
                "dispatch": self._handle_dispatch_command,
                "tmate": self._handle_tmate_command,
            },
        )

    def _handle_help_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if len(args) > 1:
            raise ValueError("/help 最多接受一個 command")
        return {
            "ok": True,
            "kind": "help",
            "text": self.command_registry.render_help(args[0] if args else None),
        }

    def _handle_status_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if args:
            raise ValueError("/status 不接受參數")
        return self.status_snapshot()

    def _handle_dispatch_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if not args:
            raise ValueError("/dispatch 需要 task_id")
        pane_idx = next((i for i, value in enumerate(args) if value.startswith("%")), None)
        if pane_idx is not None:
            pane_id = args[pane_idx]
            message = " ".join(args[pane_idx + 1:])
            if not message:
                raise ValueError(f"/dispatch {pane_id} 需要訊息內容")
            return self._send_to_pane(pane_id, message)
        return self.dispatch(" ".join(args))

    def _handle_tmate_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        raise ValueError("tmate backend 未設定")

    def handle_command(self, command: str) -> dict[str, object]:
        return self.command_dispatcher.execute(command)
```

Remove the old branch body from `handle_command()` after adding the new one.

- [ ] **Step 5: Format help result in Telegram router**

Modify `_format_message()` in `paulshaclaw/bot/telegram.py` so the first branch is:

```python
def _format_message(result: dict[str, object]) -> str:
    if result.get("kind") == "help":
        return str(result["text"])
    if "sent" in result:
        return f"已送出 -> {result['pane_id']}\n{result['sent']}"
    if "daemon" in result:
        lines = [
            f"{result['daemon']} 狀態",
            f"project={result['project']}",
            "",
            "Panes:",
            str(result.get("panes", "(unavailable)")),
        ]
        return "\n".join(lines)
    return f"已派工 {result['job_id']} -> {result['scope']}"
```

- [ ] **Step 6: Run dispatcher and smoke tests**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_command_registry tests.test_stage1_smoke -v
```

Expected: PASS for command registry tests and Stage 1 smoke tests.

- [ ] **Step 7: Commit dispatcher routing**

```bash
git add paulshaclaw/core/command_dispatcher.py paulshaclaw/core/daemon.py paulshaclaw/bot/telegram.py tests/test_stage1_command_registry.py tests/test_stage1_smoke.py
git commit -m "feat(stage1): route commands through registry dispatcher"
```

## Task 3: Telegram Command Menu Sync

**Files:**
- Modify: `paulshaclaw/bot/listener.py`
- Modify: `tests/test_telegram_listener.py`

- [ ] **Step 1: Add failing Telegram command-menu tests**

Add this test to `TelegramApiClientTests` in `tests/test_telegram_listener.py`:

```python
    def test_set_my_commands_posts_commands_payload(self) -> None:
        opener = FakeOpener([{"ok": True, "result": True}])
        client = TelegramApiClient("fake-token", opener=opener)

        client.set_my_commands(
            [
                {"command": "help", "description": "列出可用命令"},
                {"command": "tmate", "description": "管理 tmate remote access"},
            ]
        )

        body = json.loads(opener.requests[0]["data"].decode("utf-8"))
        self.assertEqual(opener.requests[0]["url"], "https://api.telegram.org/botfake-token/setMyCommands")
        self.assertEqual(
            body,
            {
                "commands": [
                    {"command": "help", "description": "列出可用命令"},
                    {"command": "tmate", "description": "管理 tmate remote access"},
                ]
            },
        )
```

Replace `ListenerMainTests.test_main_success_runs_listener` with this version:

```python
    def test_main_success_syncs_commands_before_listener_runs(self) -> None:
        fake_listener = mock.Mock()
        fake_client = mock.Mock()
        calls: list[str] = []

        def sync_commands(commands: list[dict[str, str]]) -> None:
            calls.append("set_my_commands")
            self.assertIn({"command": "tmate", "description": "管理 tmate remote access"}, commands)

        def run_forever() -> None:
            calls.append("run_forever")

        fake_client.set_my_commands.side_effect = sync_commands
        fake_listener.run_forever.side_effect = run_forever

        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")) as load_settings,
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client) as api_client,
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity") as validate_identity,
            mock.patch("paulshaclaw.bot.listener.build_listener", return_value=fake_listener) as build_listener_mock,
        ):
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, ["set_my_commands", "run_forever"])
        load_settings.assert_called_once_with()
        api_client.assert_called_once_with("fake-token")
        validate_identity.assert_called_once()
        build_listener_mock.assert_called_once()
```

Add this test to `ListenerMainTests`:

```python
    def test_main_returns_one_when_command_menu_sync_fails(self) -> None:
        fake_client = mock.Mock()
        fake_client.set_my_commands.side_effect = TelegramApiError("menu sync failed")

        with (
            mock.patch("paulshaclaw.bot.listener.load_bot_settings", return_value=BotSettings(token="fake-token")),
            mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client),
            mock.patch("paulshaclaw.bot.listener.validate_bot_identity"),
        ):
            exit_code = listener_module.main([])

        self.assertEqual(exit_code, 1)
```

- [ ] **Step 2: Run Telegram tests to verify they fail**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_telegram_listener -v
```

Expected: FAIL because `TelegramApiClient.set_my_commands` is not defined.

- [ ] **Step 3: Implement Telegram API menu methods**

In `paulshaclaw/bot/listener.py`, add these methods to `TelegramApiClient` after `send_message()`:

```python
    def set_my_commands(self, commands: list[dict[str, str]]) -> None:
        self._post("setMyCommands", {"commands": commands})

    def get_my_commands(self) -> list[dict[str, object]]:
        result = self._post("getMyCommands", {})
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getMyCommands returned non-list result")
        commands: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict):
                commands.append(item)
        return commands
```

- [ ] **Step 4: Sync registry commands in listener startup**

In `paulshaclaw/bot/listener.py`, add import:

```python
from paulshaclaw.core.command_registry import CommandRegistry, load_default_command_registry
```

Change `build_dispatch_guard_daemon()` and `build_listener()` signatures:

```python
def build_dispatch_guard_daemon(config: AppConfig, command_registry: CommandRegistry | None = None) -> PaulShiaBroDaemon:
    return PaulShiaBroDaemon(config=config, coordinator=UnavailableCoordinator(), command_registry=command_registry)
```

```python
def build_listener(
    *,
    config_path: str | None,
    settings: BotSettings,
    client: TelegramApiClient | None = None,
    poll_timeout: int = 30,
    command_registry: CommandRegistry | None = None,
) -> TelegramListener:
    config = load_config(config_path=config_path)
    resolved_registry = command_registry or load_default_command_registry()
    daemon = build_dispatch_guard_daemon(config, resolved_registry)
    router = TelegramCommandRouter(daemon=daemon)
    return TelegramListener(
        client=client or TelegramApiClient(settings.token),
        router=router,
        poll_timeout=poll_timeout,
    )
```

Update `main()` before `build_listener()`:

```python
        command_registry = load_default_command_registry()
        client.set_my_commands(command_registry.telegram_commands())
        listener = build_listener(
            config_path=args.config,
            settings=settings,
            client=client,
            poll_timeout=args.poll_timeout,
            command_registry=command_registry,
        )
```

- [ ] **Step 5: Adjust existing listener tests for the new client mock**

In `test_main_writes_ready_file_before_run_forever`, `test_main_passes_config_and_poll_timeout_to_listener_builder`, and failure tests that mock `TelegramApiClient`, return a `mock.Mock()` client with `set_my_commands.return_value = None`.

Use this local pattern in each test:

```python
fake_client = mock.Mock()
fake_client.set_my_commands.return_value = None
```

Then patch:

```python
mock.patch("paulshaclaw.bot.listener.TelegramApiClient", return_value=fake_client)
```

- [ ] **Step 6: Run Telegram tests**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_telegram_listener -v
```

Expected: PASS for Telegram listener tests.

- [ ] **Step 7: Commit Telegram menu sync**

```bash
git add paulshaclaw/bot/listener.py paulshaclaw/core/daemon.py tests/test_telegram_listener.py
git commit -m "feat(stage1): sync telegram command menu from registry"
```

## Task 4: Tmate Manager

**Files:**
- Create: `paulshaclaw/core/tmate.py`
- Create: `tests/test_stage1_tmate.py`

- [ ] **Step 1: Write failing tmate manager tests**

Create `tests/test_stage1_tmate.py`:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paulshaclaw.core.tmate import TmateManager


class FakeTmateExecutor:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.session_exists = False
        self.attached = 0
        self.links = {
            "#{tmate_ssh}": "ssh rw",
            "#{tmate_web}": "https://rw",
            "#{tmate_ssh_ro}": "ssh ro",
            "#{tmate_web_ro}": "https://ro",
        }

    def __call__(self, argv: list[str], timeout: int) -> str:
        self.calls.append(argv)
        command = argv[3]
        if command == "new-session":
            self.session_exists = True
            return ""
        if command == "has-session":
            if self.session_exists:
                return ""
            raise ValueError("no session")
        if command == "display-message":
            format_value = argv[-1]
            if format_value == "#{session_attached}":
                return str(self.attached)
            return self.links[format_value]
        if command == "kill-session":
            self.session_exists = False
            return ""
        raise AssertionError(f"unexpected command: {argv}")


class TmateManagerTests(unittest.TestCase):
    def make_manager(self, executor: FakeTmateExecutor, now: datetime) -> TmateManager:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        return TmateManager(
            executor=executor,
            now=lambda: now,
            socket_path=root / "run" / "tmate.sock",
            state_path=root / "state" / "tmate.json",
            session_name="paulshaclaw",
            timeout_seconds=3600,
        )

    def test_status_reports_stopped_when_session_absent(self) -> None:
        executor = FakeTmateExecutor()
        manager = self.make_manager(executor, datetime(2026, 5, 4, tzinfo=timezone.utc))

        result = manager.status()

        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["running"])

    def test_start_creates_session_and_returns_links(self) -> None:
        executor = FakeTmateExecutor()
        now = datetime(2026, 5, 4, tzinfo=timezone.utc)
        manager = self.make_manager(executor, now)

        result = manager.start()

        self.assertTrue(result["running"])
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["ssh"], "ssh rw")
        self.assertEqual(result["web"], "https://rw")
        self.assertEqual(result["ssh_ro"], "ssh ro")
        self.assertEqual(result["web_ro"], "https://ro")
        self.assertTrue(manager.state_path.exists())

    def test_stop_kills_session_and_clears_state(self) -> None:
        executor = FakeTmateExecutor()
        manager = self.make_manager(executor, datetime(2026, 5, 4, tzinfo=timezone.utc))
        manager.start()

        result = manager.stop()

        self.assertEqual(result["state"], "stopped")
        self.assertFalse(executor.session_exists)
        self.assertFalse(manager.state_path.exists())

    def test_cleanup_stops_no_client_session_after_timeout(self) -> None:
        executor = FakeTmateExecutor()
        first = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        current = {"now": first}
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        manager = TmateManager(
            executor=executor,
            now=lambda: current["now"],
            socket_path=root / "run" / "tmate.sock",
            state_path=root / "state" / "tmate.json",
            session_name="paulshaclaw",
            timeout_seconds=3600,
        )
        manager.start()
        executor.attached = 0

        manager.cleanup_idle()
        current["now"] = first + timedelta(seconds=3601)
        result = manager.cleanup_idle()

        self.assertEqual(result["state"], "stopped")
        self.assertFalse(executor.session_exists)

    def test_cleanup_resets_idle_when_client_attached(self) -> None:
        executor = FakeTmateExecutor()
        first = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
        current = {"now": first}
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        manager = TmateManager(
            executor=executor,
            now=lambda: current["now"],
            socket_path=root / "run" / "tmate.sock",
            state_path=root / "state" / "tmate.json",
            session_name="paulshaclaw",
            timeout_seconds=3600,
        )
        manager.start()
        executor.attached = 0
        manager.cleanup_idle()
        executor.attached = 1

        result = manager.cleanup_idle()
        state = json.loads(manager.state_path.read_text(encoding="utf-8"))

        self.assertEqual(result["state"], "running")
        self.assertIsNone(state.get("last_no_client_at"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tmate tests to verify they fail**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_tmate -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.core.tmate'`.

- [ ] **Step 3: Implement tmate manager**

Create `paulshaclaw/core/tmate.py`:

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


Executor = Callable[[list[str], int], str]
Clock = Callable[[], datetime]


def default_tmate_executor(argv: list[str], timeout: int) -> str:
    try:
        completed = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise ValueError("tmate not found") from error
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"tmate command timed out after {timeout}s") from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        raise ValueError(stderr or f"tmate command failed with exit code {error.returncode}") from error
    return completed.stdout.strip()


@dataclass
class TmateManager:
    executor: Executor = default_tmate_executor
    now: Clock = lambda: datetime.now(timezone.utc)
    socket_path: Path = Path.home() / ".agents" / "run" / "paulshaclaw-tmate.sock"
    state_path: Path = Path.home() / ".agents" / "state" / "tmate.json"
    session_name: str = "paulshaclaw"
    timeout_seconds: int = 3600
    command_timeout_seconds: int = 10

    def status(self) -> dict[str, object]:
        if not self._has_session():
            self._clear_state()
            return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}
        attached = self._attached_clients()
        result = self._link_result()
        result.update({"attached_clients": attached, "timeout_seconds": self.timeout_seconds})
        self._write_state(self._state_with_last_no_client(None if attached > 0 else self._load_state().get("last_no_client_at")))
        return result

    def start(self) -> dict[str, object]:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._has_session():
            self._run(["new-session", "-d", "-s", self.session_name])
            self._write_state(
                {
                    "socket_path": str(self.socket_path),
                    "session_name": self.session_name,
                    "started_at": self._now_iso(),
                    "last_no_client_at": self._now_iso(),
                    "timeout_seconds": self.timeout_seconds,
                }
            )
        return self.status()

    def stop(self) -> dict[str, object]:
        if self._has_session():
            self._run(["kill-session", "-t", self.session_name])
        self._clear_state()
        return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}

    def cleanup_idle(self) -> dict[str, object]:
        if not self._has_session():
            self._clear_state()
            return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}

        attached = self._attached_clients()
        state = self._load_state()
        if attached > 0:
            state["last_no_client_at"] = None
            self._write_state(state)
            return {"ok": True, "kind": "tmate", "state": "running", "running": True, "attached_clients": attached}

        last_no_client_at = state.get("last_no_client_at")
        if not isinstance(last_no_client_at, str):
            state["last_no_client_at"] = self._now_iso()
            self._write_state(state)
            return {"ok": True, "kind": "tmate", "state": "running", "running": True, "attached_clients": 0}

        idle_for = (self.now() - datetime.fromisoformat(last_no_client_at)).total_seconds()
        if idle_for >= self.timeout_seconds:
            return self.stop()
        return {"ok": True, "kind": "tmate", "state": "running", "running": True, "attached_clients": 0}

    def _link_result(self) -> dict[str, object]:
        try:
            ssh = self._display("#{tmate_ssh}")
            web = self._display("#{tmate_web}")
            ssh_ro = self._display("#{tmate_ssh_ro}")
            web_ro = self._display("#{tmate_web_ro}")
        except ValueError:
            return {"ok": True, "kind": "tmate", "state": "pending", "running": True}
        if not all([ssh, web, ssh_ro, web_ro]):
            return {"ok": True, "kind": "tmate", "state": "pending", "running": True}
        return {
            "ok": True,
            "kind": "tmate",
            "state": "running",
            "running": True,
            "ssh": ssh,
            "web": web,
            "ssh_ro": ssh_ro,
            "web_ro": web_ro,
        }

    def _has_session(self) -> bool:
        try:
            self._run(["has-session", "-t", self.session_name])
            return True
        except ValueError:
            return False

    def _attached_clients(self) -> int:
        raw = self._display("#{session_attached}")
        return int(raw or "0")

    def _display(self, fmt: str) -> str:
        return self._run(["display-message", "-p", fmt])

    def _run(self, args: list[str]) -> str:
        argv = ["tmate", "-S", str(self.socket_path), *args]
        return self.executor(argv, self.command_timeout_seconds)

    def _load_state(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {
                "socket_path": str(self.socket_path),
                "session_name": self.session_name,
                "started_at": self._now_iso(),
                "last_no_client_at": None,
                "timeout_seconds": self.timeout_seconds,
            }
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def _clear_state(self) -> None:
        self.state_path.unlink(missing_ok=True)

    def _state_with_last_no_client(self, value: object) -> dict[str, object]:
        state = self._load_state()
        state["last_no_client_at"] = value
        state["timeout_seconds"] = self.timeout_seconds
        return state

    def _now_iso(self) -> str:
        return self.now().isoformat()
```

- [ ] **Step 4: Run tmate manager tests**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_tmate -v
```

Expected: PASS for tmate manager tests.

- [ ] **Step 5: Commit tmate manager**

```bash
git add paulshaclaw/core/tmate.py tests/test_stage1_tmate.py
git commit -m "feat(stage1): add managed tmate runtime"
```

## Task 5: Tmate Command Integration And Redaction

**Files:**
- Modify: `paulshaclaw/core/daemon.py`
- Modify: `paulshaclaw/bot/telegram.py`
- Modify: `paulshaclaw/bot/listener.py`
- Modify: `tests/test_stage1_smoke.py`
- Modify: `tests/test_telegram_listener.py`

- [ ] **Step 1: Add failing integration tests**

Append this test to `Stage1SmokeTest` in `tests/test_stage1_smoke.py`:

```python
    def test_tmate_bare_command_returns_status(self) -> None:
        class FakeTmateManager:
            def __init__(self) -> None:
                self.status_calls = 0

            def status(self) -> dict[str, object]:
                self.status_calls += 1
                return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}

            def start(self) -> dict[str, object]:
                raise AssertionError("start should not be called")

            def stop(self) -> dict[str, object]:
                raise AssertionError("stop should not be called")

            def cleanup_idle(self) -> dict[str, object]:
                return {"ok": True, "kind": "tmate", "state": "stopped", "running": False}

        config_path = self.make_config_path()
        tmate_manager = FakeTmateManager()
        daemon = PaulShiaBroDaemon(
            config=load_config(config_path=config_path),
            coordinator=FakeCoordinator(),
            tmate_manager=tmate_manager,
        )
        router = TelegramCommandRouter(daemon=daemon)

        result = router.handle_message(user_id=1001, text="/tmate")

        self.assertTrue(result["ok"])
        self.assertIn("tmate: stopped", result["message"])
        self.assertEqual(tmate_manager.status_calls, 1)
```

Add these tests to `TelegramListenerTests` in `tests/test_telegram_listener.py`:

```python
    def test_run_once_calls_cleanup_even_without_updates(self) -> None:
        client = RecordingClient([])
        cleanup_calls: list[str] = []
        listener = TelegramListener(
            client=client,
            router=FakeRouter({"ok": True, "message": "ok"}),
            cleanup=lambda: cleanup_calls.append("cleanup"),
        )

        listener.run_once()

        self.assertEqual(cleanup_calls, ["cleanup"])
        self.assertEqual(client.get_updates_calls, [{"offset": None, "timeout": 30}])

    def test_safe_send_redacts_tmate_links_in_logs(self) -> None:
        client = RecordingClient([])
        listener = TelegramListener(client=client, router=FakeRouter({"ok": True, "message": "ok"}))

        with self.assertLogs("paulshaclaw.bot.listener", level="INFO") as logs:
            listener._safe_send(chat_id=1001, text="ssh session: ssh abc@tmate.io\nweb: https://tmate.io/t/secret")

        self.assertEqual(len(client.sent_messages), 1)
        joined = "\n".join(logs.output)
        self.assertIn("<redacted>", joined)
        self.assertNotIn("abc@tmate.io", joined)
        self.assertNotIn("https://tmate.io/t/secret", joined)
```

- [ ] **Step 2: Run integration tests to verify they fail**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_smoke.Stage1SmokeTest.test_tmate_bare_command_returns_status tests.test_telegram_listener.TelegramListenerTests.test_run_once_calls_cleanup_even_without_updates tests.test_telegram_listener.TelegramListenerTests.test_safe_send_redacts_tmate_links_in_logs -v
```

Expected: FAIL because daemon has no `tmate_manager` constructor argument and listener has no cleanup callback/redaction.

- [ ] **Step 3: Wire tmate manager into daemon**

Modify imports in `paulshaclaw/core/daemon.py`:

```python
from paulshaclaw.core.tmate import TmateManager
```

Change constructor signature and body:

```python
    def __init__(
        self,
        config: AppConfig,
        coordinator: CoordinatorClient | None = None,
        command_registry: CommandRegistry | None = None,
        tmate_manager: TmateManager | None = None,
    ) -> None:
        self.config = config
        self.coordinator = coordinator or LocalCoordinator()
        self.command_registry = command_registry or load_default_command_registry()
        tmate_command = self.command_registry.get("/tmate")
        tmate_timeout = tmate_command.func_call.timeout_seconds or 3600
        self.tmate_manager = tmate_manager or TmateManager(timeout_seconds=tmate_timeout)
        self.command_dispatcher = CommandDispatcher(
            self.command_registry,
            python_handlers={
                "help": self._handle_help_command,
                "status": self._handle_status_command,
                "dispatch": self._handle_dispatch_command,
                "tmate": self._handle_tmate_command,
            },
        )
```

Replace `_handle_tmate_command()` and cleanup method:

```python
    def _handle_tmate_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        subcommand = args[0] if args else "status"
        if len(args) > 1:
            raise ValueError("/tmate 只接受 status/start/stop")
        if subcommand == "status":
            return self.tmate_manager.status()
        if subcommand == "start":
            return self.tmate_manager.start()
        if subcommand == "stop":
            return self.tmate_manager.stop()
        raise ValueError("/tmate 只接受 status/start/stop")

    def cleanup_idle_resources(self) -> None:
        self.tmate_manager.cleanup_idle()
```

- [ ] **Step 4: Format tmate responses**

Modify `_format_message()` in `paulshaclaw/bot/telegram.py` by inserting this branch after help:

```python
    if result.get("kind") == "tmate":
        state = str(result.get("state", "unknown"))
        if state == "running" and all(key in result for key in ("ssh", "web", "ssh_ro", "web_ro")):
            return "\n".join(
                [
                    "tmate: running",
                    f"ssh: {result['ssh']}",
                    f"web: {result['web']}",
                    f"ssh_ro: {result['ssh_ro']}",
                    f"web_ro: {result['web_ro']}",
                ]
            )
        return f"tmate: {state}"
```

- [ ] **Step 5: Add listener cleanup callback and redaction**

Modify `TelegramListener.__init__` in `paulshaclaw/bot/listener.py`:

```python
    def __init__(
        self,
        *,
        client: TelegramApiClient,
        router: TelegramCommandRouter,
        poll_timeout: int = 30,
        sleep: Callable[[float], None] = time.sleep,
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        self.client = client
        self.router = router
        self.poll_timeout = poll_timeout
        self.sleep = sleep
        self.cleanup = cleanup or (lambda: None)
        self.offset: int | None = None
        self.max_backoff = 30.0
```

At the start of `run_once()`:

```python
    def run_once(self) -> None:
        self.cleanup()
        updates = self.client.get_updates(offset=self.offset, timeout=self.poll_timeout)
        for update in updates:
            next_offset = self._next_offset(update)
            self.process_update(update)
            if next_offset is not None:
                self.offset = next_offset
```

Add redaction helper near `TelegramApiError`:

```python
def redact_sensitive_text(text: str) -> str:
    words = []
    for word in text.split():
        if "tmate.io" in word or word.startswith("ssh://"):
            words.append("<redacted>")
        else:
            words.append(word)
    return " ".join(words)
```

Change `_safe_send()` logging:

```python
    def _safe_send(self, *, chat_id: int, text: str) -> None:
        logger.info("OUT chat=%d text=%r", chat_id, redact_sensitive_text(text))
        try:
            self.client.send_message(chat_id=chat_id, text=text)
        except TelegramApiError as error:
            logger.error("SEND_ERROR chat=%d error=%s", chat_id, error)
```

Change the `build_listener()` return block to pass the daemon cleanup hook:

```python
    return TelegramListener(
        client=client or TelegramApiClient(settings.token),
        router=router,
        poll_timeout=poll_timeout,
        cleanup=daemon.cleanup_idle_resources,
    )
```

- [ ] **Step 6: Run integration tests**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_smoke tests.test_telegram_listener -v
```

Expected: PASS for Stage 1 smoke and Telegram listener tests.

- [ ] **Step 7: Commit tmate command integration**

```bash
git add paulshaclaw/core/daemon.py paulshaclaw/bot/telegram.py paulshaclaw/bot/listener.py tests/test_stage1_smoke.py tests/test_telegram_listener.py
git commit -m "feat(stage1): expose managed tmate command"
```

## Task 6: Final Verification And OpenSpec Traceability

**Files:**
- Verify: `openspec/changes/stage1-tmate-command-registry/proposal.md`
- Verify: `openspec/changes/stage1-tmate-command-registry/design.md`
- Verify: `openspec/changes/stage1-tmate-command-registry/specs/stage1-core-runtime/spec.md`
- Verify: `openspec/changes/stage1-tmate-command-registry/tasks.md`

- [ ] **Step 1: Run targeted test set**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_stage1_command_registry tests.test_stage1_tmate tests.test_stage1_smoke tests.test_telegram_listener -v
```

Expected: PASS for all targeted Stage 1 command, tmate, smoke, and Telegram listener tests.

- [ ] **Step 2: Run full unittest discovery**

Run:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

Expected: PASS for the full repository test suite.

- [ ] **Step 3: Validate OpenSpec change**

Run:

```bash
openspec validate stage1-tmate-command-registry
openspec status --change stage1-tmate-command-registry
```

Expected:

```text
Change 'stage1-tmate-command-registry' is valid
All artifacts complete!
```

- [ ] **Step 4: Update OpenSpec task checkboxes**

Edit `openspec/changes/stage1-tmate-command-registry/tasks.md` and mark each completed implementation task with `[x]`.

- [ ] **Step 5: Commit verification state**

```bash
git add openspec/changes/stage1-tmate-command-registry/tasks.md
git commit -m "chore(stage1): mark tmate command registry tasks complete"
```
