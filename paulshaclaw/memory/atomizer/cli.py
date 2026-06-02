from __future__ import annotations

import argparse
import json
import shlex
from collections.abc import Mapping
from pathlib import Path

from .agent_exec import AgentExecClient, CachingAgentClient
from . import config as atomizer_config
from . import pipeline
from .llm_promoter import LLMPromoter
from .promoter import IdentityPromoter, Promoter


def _known_projects(path_str: str) -> list[str]:
    path = Path(path_str).expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError):
        return []

    try:
        import yaml
    except ModuleNotFoundError:
        return []

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(data, Mapping):
        return []

    projects = data.get("projects")
    if isinstance(projects, Mapping):
        return [
            str(name)
            for name in projects.keys()
            if isinstance(name, str) and atomizer_config.is_safe_path_component(name)
        ]
    if isinstance(projects, list):
        names: list[str] = []
        for item in projects:
            if isinstance(item, str) and atomizer_config.is_safe_path_component(item):
                names.append(item)
            elif isinstance(item, Mapping):
                name = item.get("name")
                if isinstance(name, str) and atomizer_config.is_safe_path_component(name):
                    names.append(name)
        return names
    return []


def _resolve_skill_path(config: atomizer_config.AtomizerConfig) -> Path:
    path = Path(config.skill_path).expanduser()
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parent / path


def _cache_dir(memory_root: Path) -> Path:
    return memory_root / "runtime" / "cache" / "atomize"


def _build_promoter(
    args: argparse.Namespace,
    config: atomizer_config.AtomizerConfig,
    memory_root: Path,
) -> Promoter:
    promoter_name = args.promoter or config.default_promoter
    if promoter_name != "llm":
        return IdentityPromoter()

    command = (
        list(atomizer_config.resolve_command_argv(shlex.split(args.agent_command)))
        if args.agent_command is not None
        else list(atomizer_config.resolve_command_argv(config.agent_exec_command))
    )
    inner = AgentExecClient(command, timeout=config.agent_exec_timeout)
    cached_client = CachingAgentClient(
        inner,
        _cache_dir(memory_root),
    )
    skill_path = _resolve_skill_path(config)
    skill_text = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    return LLMPromoter(
        cached_client,
        skill_text,
        _known_projects(config.known_projects_file),
        model=config.agent_exec_model,
    )


def run(args: argparse.Namespace) -> int:
    override = args.override if getattr(args, "override", None) else atomizer_config._DEFAULT_SENTINEL
    config, config_hash = atomizer_config.load_config(override_path=override)
    memory_root = Path(args.memory_root)
    promoter = _build_promoter(args, config, memory_root)
    result = pipeline.run(
        memory_root,
        config=config,
        config_hash=config_hash,
        now=args.now,
        dry_run=args.dry_run,
        promoter=promoter,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0
