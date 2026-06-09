import unittest

from paulshaclaw.core.command_dispatcher import CommandDispatcher, expand_shell_argv
from paulshaclaw.core.command_registry import (
    CommandRegistryError,
    load_default_command_registry,
    parse_command_registry,
)


class CommandRegistryTests(unittest.TestCase):
    def test_load_default_command_registry_order_and_commands(self) -> None:
        registry = load_default_command_registry()
        self.assertEqual(
            [command.name for command in registry.commands],
            ["/help", "/status", "/dispatch", "/tmate", "/agent"],
        )
        self.assertEqual(
            registry.telegram_commands(),
            [
                {"command": "help", "description": "列出可用命令"},
                {"command": "status", "description": "顯示 runtime 狀態"},
                {"command": "dispatch", "description": "派工或送訊息到 pane"},
                {"command": "tmate", "description": "管理 tmate remote access"},
                {"command": "agent", "description": "管理 claude-gemma4 agent"},
            ],
        )
        self.assertTrue(all(command.telegram_menu.enabled for command in registry.commands))
        self.assertEqual(registry.get("/tmate").func_call.timeout_seconds, 3600)
        self.assertEqual(registry.get("/agent").func_call.type, "python")
        self.assertEqual(registry.get("/agent").func_call.target, "agent")

    def test_duplicate_command_names_raise(self) -> None:
        with self.assertRaisesRegex(CommandRegistryError, "duplicate command"):
            parse_command_registry(
                {
                    "version": 1,
                    "defaults": {"timeout_seconds": 30},
                    "commands": [
                        {
                            "name": "/help",
                            "usage": "/help",
                            "summary": "a",
                            "telegram_menu": {"command": "help", "description": "x"},
                            "func_call": {"type": "python", "target": "help"},
                        },
                        {
                            "name": "/help",
                            "usage": "/help",
                            "summary": "b",
                            "telegram_menu": {"command": "help2", "description": "y"},
                            "func_call": {"type": "python", "target": "help"},
                        },
                    ],
                }
            )

    def test_invalid_telegram_menu_command_raises(self) -> None:
        with self.assertRaisesRegex(CommandRegistryError, "telegram_menu.command"):
            parse_command_registry(
                {
                    "version": 1,
                    "defaults": {"timeout_seconds": 30},
                    "commands": [
                        {
                            "name": "/help",
                            "usage": "/help",
                            "summary": "a",
                            "telegram_menu": {"command": "/help", "description": "x"},
                            "func_call": {"type": "python", "target": "help"},
                        }
                    ],
                }
            )

    def test_unknown_shell_placeholder_raises(self) -> None:
        with self.assertRaisesRegex(CommandRegistryError, "unsupported placeholder"):
            parse_command_registry(
                {
                    "version": 1,
                    "defaults": {"timeout_seconds": 30},
                    "commands": [
                        {
                            "name": "/dispatch",
                            "usage": "/dispatch <task_id>|<pane_id> <message>",
                            "summary": "a",
                            "telegram_menu": {"command": "dispatch", "description": "x"},
                            "func_call": {
                                "type": "shell",
                                "argv": ["echo", "{unsafe}"],
                            },
                        }
                    ],
                }
            )

    def test_render_help_uses_registry_metadata(self) -> None:
        registry = load_default_command_registry()
        help_text = registry.render_help()
        self.assertIn("/help [command] - 列出可用命令，或顯示單一命令用法", help_text)
        self.assertIn("/agent [start %pane|startf %pane|stop|status] - 管理 claude-gemma4 agent session", help_text)
        self.assertIn("/tmate [status|start|stop]", registry.render_help("/tmate"))
        self.assertEqual(registry.render_help("tmate"), registry.render_help("/tmate"))

    def test_dispatcher_routes_python_and_shell_commands(self) -> None:
        registry = load_default_command_registry()
        calls: list[tuple[list[str], object]] = []
        shell_calls: list[tuple[list[str], int]] = []

        def handle_status(args: list[str], command: object) -> dict[str, object]:
            calls.append((args, command))
            return {"ok": True, "kind": "status", "args": args}

        dispatcher = CommandDispatcher(
            registry=registry,
            python_handlers={"status": handle_status},
            shell_executor=lambda argv, timeout: "hello" if argv == ["printf", "hello"] and timeout == 9 else "unexpected",
        )

        self.assertEqual(dispatcher.execute("/status"), {"ok": True, "kind": "status", "args": []})

        shell_registry = parse_command_registry(
            {
                "version": 1,
                "defaults": {"timeout_seconds": 30},
                "commands": [
                    {
                        "name": "/echo",
                        "usage": "/echo <message>",
                        "summary": "echo",
                        "telegram_menu": {"command": "echo", "description": "echo"},
                        "func_call": {
                            "type": "shell",
                            "argv": ["printf", "{arg0}"],
                            "timeout_seconds": 9,
                        },
                    }
                ],
            }
        )
        shell_dispatcher = CommandDispatcher(
            registry=shell_registry,
            python_handlers={},
            shell_executor=lambda argv, timeout: shell_calls.append((argv, timeout)) or "hello",
        )
        self.assertEqual(shell_dispatcher.execute("/echo hello"), {"ok": True, "kind": "shell", "stdout": "hello"})
        self.assertEqual(calls[0][0], [])
        self.assertEqual(shell_calls[0], (["printf", "hello"], 9))

    def test_expand_shell_argv_supports_args_and_indexed_args(self) -> None:
        self.assertEqual(
            expand_shell_argv(["printf", "{args}", "{arg0}", "{arg1}"], ["hello", "world"]),
            ["printf", "hello world", "hello", "world"],
        )

    def test_unknown_command_raises_value_error(self) -> None:
        registry = load_default_command_registry()
        dispatcher = CommandDispatcher(registry=registry, python_handlers={})

        with self.assertRaisesRegex(ValueError, "不支援的指令"):
            dispatcher.execute("/unknown")


if __name__ == "__main__":
    unittest.main()
