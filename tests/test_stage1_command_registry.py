import unittest

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
        self.assertTrue(all(command.telegram_menu.enabled for command in registry.commands))
        self.assertEqual(registry.get("/tmate").func_call.timeout_seconds, 3600)

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
        self.assertIn("/tmate [status|start|stop]", registry.render_help("/tmate"))
        self.assertEqual(registry.render_help("tmate"), registry.render_help("/tmate"))


if __name__ == "__main__":
    unittest.main()
