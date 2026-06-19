from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

from .contract import PersonaContract, validate_persona_schema

DEFAULT_PERSONAS_PATH = Path(__file__).with_name("personas.yaml")


def load_catalog(path: str | Path | None = None) -> dict[str, PersonaContract]:
    source = Path(path) if path is not None else DEFAULT_PERSONAS_PATH
    if not source.is_file():
        raise FileNotFoundError(f"persona catalog 不存在: {source}")
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"persona catalog 解析失敗: {source}: {exc}") from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("roles"), Mapping):
        raise ValueError(f"persona catalog 格式錯誤（缺 roles）: {source}")

    records = raw["roles"]
    result = validate_persona_schema(records)
    if not result.ok:
        raise ValueError(f"persona catalog schema 不合法: {result.errors}")

    catalog: dict[str, PersonaContract] = {}
    for role, rec in records.items():
        catalog[role] = PersonaContract(
            role=rec["role"],
            version=rec["version"],
            summary=rec["summary"],
            allowed_phases=tuple(rec["allowed_phases"]),
            write_paths=tuple(rec["write_paths"]),
            allowed_tools=tuple(rec["allowed_tools"]),
        )
    return catalog
