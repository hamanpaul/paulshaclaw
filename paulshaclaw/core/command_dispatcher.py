from __future__ import annotations

import shlex
import subprocess
from typing import Callable

from paulshaclaw.core.command_registry import CommandRegistry, CommandRegistryError, CommandSpec


PythonHandler = Callable[[list[str], CommandSpec], dict[str, object]]
ShellExecutor = Callable[[list[str], int], str]


class CommandDispatcher:
    def __init__(
        self,
        registry: CommandRegistry,
        python_handlers: dict[str, PythonHandler],
        shell_executor: ShellExecutor | None = None,
    ) -> None:
        self.registry = registry
        self.python_handlers = python_handlers
        self.shell_executor = shell_executor or default_shell_executor

    def execute(self, command_text: str) -> dict[str, object]:
        normalized = command_text.strip()
        if not normalized:
            raise ValueError("不支援的指令: ")

        try:
            parts = shlex.split(normalized)
        except ValueError as exc:
            raise ValueError(f"不支援的指令: {normalized}") from exc
        if not parts:
            raise ValueError("不支援的指令: ")

        command_name, args = parts[0], parts[1:]
        try:
            command = self.registry.get(command_name)
        except CommandRegistryError as exc:
            raise ValueError(f"不支援的指令: {normalized}") from exc

        if command.func_call.type == "python":
            handler_name = command.func_call.target or command.name.lstrip("/")
            handler = self.python_handlers.get(handler_name)
            if handler is None:
                raise ValueError(f"不支援的指令: {normalized}")
            return handler(args, command)

        if command.func_call.type == "shell":
            timeout = command.func_call.timeout_seconds or self.registry.default_timeout_seconds
            if timeout is None:
                timeout = 0
            argv = expand_shell_argv(list(command.func_call.argv), args)
            stdout = self.shell_executor(argv, timeout)
            return {"ok": True, "kind": "shell", "stdout": stdout}

        raise ValueError(f"不支援的指令: {normalized}")


def expand_shell_argv(argv: list[str], args: list[str]) -> list[str]:
    expanded: list[str] = []
    for token in argv:
        replaced = token.replace("{args}", " ".join(args))
        for index, arg in enumerate(args):
            replaced = replaced.replace(f"{{arg{index}}}", arg)
        if "{arg" in replaced:
            raise ValueError("shell command argument missing")
        expanded.append(replaced)
    return expanded


def default_shell_executor(argv: list[str], timeout: int) -> str:
    try:
        completed = subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"shell command timeout: {timeout}s") from exc
    except FileNotFoundError as exc:
        raise ValueError(f"shell command not found: {argv[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(stderr or f"shell command failed: exit {exc.returncode}") from exc
    return completed.stdout
