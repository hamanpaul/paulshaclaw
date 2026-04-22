from __future__ import annotations

import json
from pathlib import Path

from .models import JobSummary


class ArtifactAdapter:
    def __init__(self, *, coordinator_jobs_dir: Path | None = None) -> None:
        self.coordinator_jobs_dir = coordinator_jobs_dir

    def load_jobs_by_pane(self) -> dict[str, tuple[JobSummary, ...]]:
        if self.coordinator_jobs_dir is None or not self.coordinator_jobs_dir.exists():
            return {}

        jobs_by_pane: dict[str, list[JobSummary]] = {}
        for job_path in sorted(self.coordinator_jobs_dir.glob("*.json")):
            try:
                payload = json.loads(job_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue

            nested_payload = payload.get("payload")
            pane_id = payload.get("pane_id")
            if not pane_id and isinstance(nested_payload, dict):
                pane_id = nested_payload.get("pane_id")
            if not pane_id:
                continue

            jobs_by_pane.setdefault(str(pane_id), []).append(
                JobSummary(
                    source="coordinator",
                    status=str(payload.get("status", payload.get("phase", "unknown"))),
                    trace_id=_as_optional_string(payload.get("trace_id")),
                    pane_id=str(pane_id),
                    scope=_as_optional_string(payload.get("scope")),
                )
            )

        return {pane_id: tuple(items) for pane_id, items in jobs_by_pane.items()}


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
