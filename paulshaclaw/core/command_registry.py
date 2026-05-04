from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


TELEGRAM_COMMAND_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class CommandRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramMenu:
    command: str
    description: str
    enabled: bool = True


@dataclass(frozen=True)
class FuncCall:
    type: str
    target: str | None = None
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
    version: int
    defaults_timeout_seconds: int | None
    commands: tuple[CommandSpec, ...]

    @property
    def default_timeout_seconds(self) -> int | None:
        return self.defaults_timeout_seconds

    def get(self, name: str) -> CommandSpec:
        normalized = _normalize_command_name(name)
        for command in self.commands:
            if _normalize_command_name(command.name) == normalized:
                return command
        raise CommandRegistryError(f"unknown command: {name}")

    def telegram_commands(self) -> list[dict[str, str]]:
        commands: list[dict[str, str]] = []
        for command in self.commands:
            if command.telegram_menu.enabled:
                commands.append(
                    {
                        "command": command.telegram_menu.command,
                        "description": command.telegram_menu.description,
                    }
                )
        return commands

    def render_help(self, command_name: str | None = None) -> str:
        if command_name is None:
            return "\n".join(f"{command.usage} - {command.summary}" for command in self.commands)
        command = self.get(command_name)
        return f"{command.usage} - {command.summary}"


def load_default_command_registry() -> CommandRegistry:
    return load_command_registry(Path(__file__).with_name("commands.json"))


def load_command_registry(path: str | Path) -> CommandRegistry:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise CommandRegistryError("command registry payload must be an object")
    return parse_command_registry(payload)


def parse_command_registry(payload: Mapping[str, Any]) -> CommandRegistry:
    if not isinstance(payload, Mapping):
        raise CommandRegistryError("command registry payload must be an object")

    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise CommandRegistryError("unsupported registry version")

    defaults = payload.get("defaults", {})
    if not isinstance(defaults, Mapping):
        raise CommandRegistryError("defaults must be an object")
    defaults_timeout_seconds = _optional_positive_int(defaults.get("timeout_seconds"), "defaults.timeout_seconds")

    raw_commands = payload.get("commands")
    if not isinstance(raw_commands, list):
        raise CommandRegistryError("commands must be a list")

    commands: list[CommandSpec] = []
    seen_names: set[str] = set()
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, Mapping):
            raise CommandRegistryError(f"commands[{index}] must be an object")

        name = _require_str(raw_command, "name", f"commands[{index}].name")
        usage = _require_str(raw_command, "usage", f"commands[{index}].usage")
        summary = _require_str(raw_command, "summary", f"commands[{index}].summary")

        normalized_name = _normalize_command_name(name)
        if normalized_name in seen_names:
            raise CommandRegistryError(f"duplicate command: {name}")
        seen_names.add(normalized_name)

        telegram_menu = _parse_telegram_menu(raw_command.get("telegram_menu"), prefix=f"commands[{index}].telegram_menu")
        func_call = _parse_func_call(raw_command.get("func_call"), prefix=f"commands[{index}].func_call")
        commands.append(
            CommandSpec(
                name=name,
                usage=usage,
                summary=summary,
                telegram_menu=telegram_menu,
                func_call=func_call,
            )
        )

    return CommandRegistry(version=1, defaults_timeout_seconds=defaults_timeout_seconds, commands=tuple(commands))


def _parse_telegram_menu(payload: object, *, prefix: str) -> TelegramMenu:
    if not isinstance(payload, Mapping):
        raise CommandRegistryError(f"{prefix} must be an object")
    command = _require_str(payload, "command", f"{prefix}.command")
    description = _require_str(payload, "description", f"{prefix}.description")
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise CommandRegistryError(f"{prefix}.enabled must be a boolean")
    if not TELEGRAM_COMMAND_RE.fullmatch(command):
        raise CommandRegistryError(f"{prefix}.command invalid")
    return TelegramMenu(command=command, description=description, enabled=enabled)


def _parse_func_call(payload: object, *, prefix: str) -> FuncCall:
    if not isinstance(payload, Mapping):
        raise CommandRegistryError(f"{prefix} must be an object")
    func_type = _require_str(payload, "type", f"{prefix}.type")
    timeout_seconds = _optional_positive_int(payload.get("timeout_seconds"), f"{prefix}.timeout_seconds")
    if func_type == "python":
        target = _require_str(payload, "target", f"{prefix}.target")
        return FuncCall(type=func_type, target=target, timeout_seconds=timeout_seconds)
    if func_type == "shell":
        raw_argv = payload.get("argv")
        if not isinstance(raw_argv, list) or not raw_argv:
            raise CommandRegistryError(f"{prefix}.argv must be a non-empty list")
        argv: list[str] = []
        for index, item in enumerate(raw_argv):
            if not isinstance(item, str) or not item:
                raise CommandRegistryError(f"{prefix}.argv[{index}] must be a non-empty string")
            _validate_shell_placeholders(item)
            argv.append(item)
        return FuncCall(type=func_type, argv=tuple(argv), timeout_seconds=timeout_seconds)
    raise CommandRegistryError(f"unsupported func_call.type: {func_type}")


def _validate_shell_placeholders(value: str) -> None:
    for placeholder in PLACEHOLDER_RE.findall(value):
        if placeholder == "args":
            continue
        if not re.fullmatch(r"arg\d+", placeholder):
            raise CommandRegistryError(f"unsupported placeholder: {{{placeholder}}}")


def _optional_positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CommandRegistryError(f"{field} must be a positive integer")
    return value


def _require_str(payload: Mapping[str, Any], key: str, field: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CommandRegistryError(f"{field} must be a non-empty string")
    return value


def _normalize_command_name(name: str) -> str:
    return name[1:] if name.startswith("/") else name
