from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _require_fields(payload: Mapping[str, object], *, prefix: str, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field not in payload:
            raise ValueError(f"{prefix}.{field} 缺失")


@dataclass(frozen=True)
class CoordinatorSettings:
    phase: str
    backend: str | None
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
    def from_dict(
        cls,
        payload: Mapping[str, object],
        *,
        env: Mapping[str, str] | None = None,
    ) -> "AppConfig":
        _require_fields(
            payload,
            prefix="config",
            fields=("daemon_name", "default_project", "coordinator", "pane_assignments"),
        )
        coordinator_payload = payload.get("coordinator")
        if not isinstance(coordinator_payload, Mapping):
            raise ValueError("config.coordinator 缺失")
        _require_fields(coordinator_payload, prefix="config.coordinator", fields=("phase",))
        resolved_env = os.environ if env is None else env
        backend_override = resolved_env.get("PSC_COORDINATOR_BACKEND", "").strip() or None
        backend = backend_override
        if backend is None:
            raw_backend = coordinator_payload.get("backend")
            if raw_backend is not None:
                backend = str(raw_backend).strip() or None

        raw_panes = payload.get("pane_assignments")
        if not isinstance(raw_panes, list):
            raise ValueError("config.pane_assignments 缺失")

        pane_assignments: list[PaneAssignment] = []
        for index, item in enumerate(raw_panes):
            if not isinstance(item, Mapping):
                raise ValueError(f"config.pane_assignments[{index}] 格式錯誤")
            _require_fields(
                item,
                prefix=f"config.pane_assignments[{index}]",
                fields=("pane_id", "title", "task_id", "status"),
            )
            pane_assignments.append(
                PaneAssignment(
                    pane_id=str(item["pane_id"]),
                    title=str(item["title"]),
                    task_id=str(item["task_id"]),
                    status=str(item["status"]),
                )
            )

        return cls(
            daemon_name=str(payload["daemon_name"]),
            default_project=str(payload["default_project"]),
            allowed_user_ids=tuple(int(value) for value in payload.get("allowed_user_ids", [])),
            coordinator=CoordinatorSettings(
                phase=str(coordinator_payload["phase"]),
                backend=backend,
                default_payload=dict(coordinator_payload.get("default_payload", {})),
            ),
            pane_assignments=tuple(pane_assignments),
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
    return AppConfig.from_dict(payload, env=resolved_env)
