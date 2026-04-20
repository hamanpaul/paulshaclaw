from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CoordinatorSettings:
    phase: str
    default_payload: dict[str, object]


@dataclass(frozen=True)
class PaneAssignment:
    pane_id: str
    title: str
    task_id: str
    status: str


@dataclass(frozen=True)
class AppConfig:
    daemon_name: str
    default_project: str
    allowed_user_ids: tuple[int, ...]
    coordinator: CoordinatorSettings
    pane_assignments: tuple[PaneAssignment, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "AppConfig":
        coordinator_payload = payload.get("coordinator")
        if not isinstance(coordinator_payload, Mapping):
            raise ValueError("config.coordinator 缺失")

        raw_panes = payload.get("pane_assignments")
        if not isinstance(raw_panes, list):
            raise ValueError("config.pane_assignments 缺失")

        return cls(
            daemon_name=str(payload["daemon_name"]),
            default_project=str(payload["default_project"]),
            allowed_user_ids=tuple(int(value) for value in payload.get("allowed_user_ids", [])),
            coordinator=CoordinatorSettings(
                phase=str(coordinator_payload["phase"]),
                default_payload=dict(coordinator_payload.get("default_payload", {})),
            ),
            pane_assignments=tuple(
                PaneAssignment(
                    pane_id=str(item["pane_id"]),
                    title=str(item["title"]),
                    task_id=str(item["task_id"]),
                    status=str(item["status"]),
                )
                for item in raw_panes
            ),
        )


def load_config(
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    resolved_env = os.environ if env is None else env
    raw_path = str(config_path) if config_path is not None else resolved_env.get("PSC_STAGE1_CONFIG", "")
    if not raw_path:
        raise ValueError("需提供 --config 或 PSC_STAGE1_CONFIG")
    path = Path(raw_path)

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("設定檔格式錯誤")
    return AppConfig.from_dict(payload)
