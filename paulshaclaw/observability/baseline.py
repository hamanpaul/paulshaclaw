from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

STATUS_PRIORITY = {"pass": 0, "warn": 1, "fail": 2}


@dataclass(frozen=True)
class ProbeResult:
    name: str
    status: str
    detail: str
    observed_value: float | int
    threshold: float | int

    def as_dict(self) -> dict[str, object]:
        if self.status not in STATUS_PRIORITY:
            raise ValueError(f"未知 probe status: {self.status}")
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "observed_value": self.observed_value,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class MetricThreshold:
    warn: int
    critical: int
    unit: str
    rationale: str


@dataclass(frozen=True)
class RawLogPolicy:
    retention_days: int
    max_bytes: int
    head_bytes: int
    tail_bytes: int


DEFAULT_METRIC_THRESHOLDS: dict[str, MetricThreshold] = {
    "heartbeat_age_seconds": MetricThreshold(
        warn=30,
        critical=90,
        unit="seconds",
        rationale="超過 30 秒表示心跳延遲，超過 90 秒視為不可用。",
    ),
    "queue_backlog": MetricThreshold(
        warn=10,
        critical=25,
        unit="items",
        rationale="待處理佇列超過 10 代表需要觀察，超過 25 進入復原流程。",
    ),
    "restart_count_10m": MetricThreshold(
        warn=2,
        critical=4,
        unit="restarts/10m",
        rationale="10 分鐘內重啟兩次代表不穩定，四次以上停止自動重試。",
    ),
    "error_burst_5m": MetricThreshold(
        warn=5,
        critical=10,
        unit="errors/5m",
        rationale="5 分鐘內錯誤爆量需切到人工介入。",
    ),
    "log_disk_usage_percent": MetricThreshold(
        warn=70,
        critical=85,
        unit="percent",
        rationale="log 磁碟使用率接近滿載前先裁切與輪替。",
    ),
}

DEFAULT_RAW_LOG_POLICY = RawLogPolicy(
    retention_days=7,
    max_bytes=32_768,
    head_bytes=8_192,
    tail_bytes=8_192,
)


def build_health_report(
    *,
    generated_at: str,
    daemon_snapshot: Mapping[str, object],
    probes: Sequence[ProbeResult],
) -> dict[str, object]:
    probe_payload = [probe.as_dict() for probe in probes]
    summary = {"pass": 0, "warn": 0, "fail": 0}
    failed_components: list[str] = []
    overall = "pass"

    for probe in probe_payload:
        status = str(probe["status"])
        summary[status] += 1
        if STATUS_PRIORITY[status] > STATUS_PRIORITY[overall]:
            overall = status
        if status == "fail":
            failed_components.append(str(probe["name"]))

    return {
        "ok": overall != "fail",
        "status": overall,
        "generated_at": generated_at,
        "daemon_snapshot": dict(daemon_snapshot),
        "summary": summary,
        "failed_components": failed_components,
        "probes": probe_payload,
    }


def build_error_record(
    *,
    timestamp: str,
    component: str,
    event: str,
    message: str,
    error_type: str,
    recoverable: bool,
    action: str,
    context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "schema_version": "stage5.error.v1",
        "level": "error",
        "component": component,
        "event": event,
        "message": message,
        "error_type": error_type,
        "recoverable": recoverable,
        "action": action,
        "context": dict(context or {}),
    }


def trim_raw_log(payload: str, *, policy: RawLogPolicy = DEFAULT_RAW_LOG_POLICY) -> dict[str, object]:
    raw_bytes = payload.encode("utf-8")
    original_bytes = len(raw_bytes)
    if original_bytes <= policy.max_bytes:
        return {
            "content": payload,
            "truncated": False,
            "original_bytes": original_bytes,
            "stored_bytes": original_bytes,
            "retention_days": policy.retention_days,
        }

    head_budget = min(policy.head_bytes, original_bytes)
    tail_budget = min(policy.tail_bytes, max(0, original_bytes - head_budget))

    while True:
        removed = max(0, original_bytes - head_budget - tail_budget)
        marker = f"\n...[truncated {removed} bytes]...\n".encode("utf-8")
        total = head_budget + tail_budget + len(marker)
        if total <= policy.max_bytes:
            break
        if head_budget >= tail_budget and head_budget > 0:
            head_budget -= 1
        elif tail_budget > 0:
            tail_budget -= 1
        else:
            break

    trimmed_bytes = (
        raw_bytes[:head_budget]
        + marker
        + (raw_bytes[-tail_budget:] if tail_budget else b"")
    )
    return {
        "content": trimmed_bytes.decode("utf-8", errors="ignore"),
        "truncated": True,
        "original_bytes": original_bytes,
        "stored_bytes": len(trimmed_bytes),
        "retention_days": policy.retention_days,
    }


def build_chaos_matrix(*, run_id: str) -> dict[str, object]:
    scenarios = (
        {
            "name": "tmux-server-crash",
            "fault": "kill tmux server process or remove socket",
            "expected_status": "recovered",
            "checks": [
                "tmux ls",
                "python3 -m paulshaclaw.core.daemon --command /status",
                "確認 pane 標題與 task id 已重建",
            ],
            "evidence_files": [
                f"evidence/{run_id}-tmux-server-crash-before.log",
                f"evidence/{run_id}-tmux-server-crash-after.log",
            ],
        },
        {
            "name": "full-runtime-restart",
            "fault": "restart daemon, bot listener, janitor placeholder",
            "expected_status": "recovered",
            "checks": [
                "systemctl --user status paulshaclaw-daemon.service",
                "systemctl --user status paulshaclaw-bot.service",
                "systemctl --user status paulshaclaw-janitor.service",
            ],
            "evidence_files": [
                f"evidence/{run_id}-full-runtime-restart-before.log",
                f"evidence/{run_id}-full-runtime-restart-after.log",
            ],
        },
        {
            "name": "memory-pipeline-backpressure",
            "fault": "inject backlog until queue_backlog warn threshold",
            "expected_status": "degraded",
            "checks": [
                "檢查 queue_backlog 與 error_burst_5m 指標",
                "確認 raw log 已裁切且保留尾端錯誤樣本",
            ],
            "evidence_files": [
                f"evidence/{run_id}-memory-pipeline-backpressure.log",
            ],
        },
    )
    return {
        "schema_version": "stage5.chaos-matrix.v1",
        "run_id": run_id,
        "scenarios": list(scenarios),
    }
