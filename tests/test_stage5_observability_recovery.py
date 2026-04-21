from __future__ import annotations

import json
import unittest

from paulshaclaw.observability import baseline


class HealthProbeTests(unittest.TestCase):
    def test_health_report_aggregates_probe_status_and_counts(self) -> None:
        report = baseline.build_health_report(
            generated_at="2026-04-21T00:00:00Z",
            daemon_snapshot={"daemon": "paulshaclaw", "project": "stage5-demo"},
            probes=(
                baseline.ProbeResult(name="daemon", status="pass", detail="heartbeat fresh", observed_value=3, threshold=30),
                baseline.ProbeResult(name="memory_pipeline", status="warn", detail="queue backlog elevated", observed_value=12, threshold=10),
                baseline.ProbeResult(name="tmux_server", status="fail", detail="server socket missing", observed_value=1, threshold=0),
            ),
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["pass"], 1)
        self.assertEqual(report["summary"]["warn"], 1)
        self.assertEqual(report["summary"]["fail"], 1)
        self.assertEqual(report["failed_components"], ["tmux_server"])


class ErrorRecordTests(unittest.TestCase):
    def test_error_record_has_audit_ready_shape(self) -> None:
        record = baseline.build_error_record(
            timestamp="2026-04-21T00:00:00Z",
            component="tmux-supervisor",
            event="restart-failed",
            message="tmux restart exceeded budget",
            error_type="RuntimeError",
            recoverable=False,
            action="page-operator",
            context={"attempt": 4, "session": "ops"},
        )

        self.assertEqual(
            sorted(record.keys()),
            [
                "action",
                "component",
                "context",
                "error_type",
                "event",
                "level",
                "message",
                "recoverable",
                "schema_version",
                "timestamp",
            ],
        )
        self.assertEqual(record["level"], "error")
        self.assertEqual(record["schema_version"], "stage5.error.v1")
        self.assertFalse(record["recoverable"])
        self.assertEqual(json.loads(json.dumps(record))["context"]["attempt"], 4)


class ThresholdTests(unittest.TestCase):
    def test_default_metric_thresholds_cover_core_stage5_signals(self) -> None:
        thresholds = baseline.DEFAULT_METRIC_THRESHOLDS

        self.assertEqual(thresholds["heartbeat_age_seconds"].warn, 30)
        self.assertEqual(thresholds["heartbeat_age_seconds"].critical, 90)
        self.assertEqual(thresholds["queue_backlog"].warn, 10)
        self.assertEqual(thresholds["queue_backlog"].critical, 25)
        self.assertEqual(thresholds["restart_count_10m"].warn, 2)
        self.assertEqual(thresholds["restart_count_10m"].critical, 4)
        self.assertEqual(thresholds["error_burst_5m"].warn, 5)
        self.assertEqual(thresholds["error_burst_5m"].critical, 10)
        self.assertEqual(thresholds["log_disk_usage_percent"].warn, 70)
        self.assertEqual(thresholds["log_disk_usage_percent"].critical, 85)


class RawLogPolicyTests(unittest.TestCase):
    def test_trim_raw_log_retains_head_tail_and_marks_truncation(self) -> None:
        payload = "HEADER\n" + ("A" * 80) + "\n" + ("B" * 80) + "\nTAIL"

        trimmed = baseline.trim_raw_log(
            payload,
            policy=baseline.RawLogPolicy(retention_days=7, max_bytes=90, head_bytes=32, tail_bytes=24),
        )

        self.assertTrue(trimmed["truncated"])
        self.assertEqual(trimmed["retention_days"], 7)
        self.assertLessEqual(trimmed["stored_bytes"], 90)
        self.assertIn("HEADER", trimmed["content"])
        self.assertIn("TAIL", trimmed["content"])
        self.assertIn("...[truncated", trimmed["content"])


class ChaosMatrixTests(unittest.TestCase):
    def test_recovery_and_chaos_cases_cover_tmux_restart_paths(self) -> None:
        matrix = baseline.build_chaos_matrix(run_id="20260421T120000+0800")
        scenario_names = [scenario["name"] for scenario in matrix["scenarios"]]

        self.assertIn("tmux-server-crash", scenario_names)
        self.assertIn("full-runtime-restart", scenario_names)

        tmux_case = next(item for item in matrix["scenarios"] if item["name"] == "tmux-server-crash")
        self.assertEqual(tmux_case["expected_status"], "recovered")
        self.assertIn("tmux ls", " ".join(tmux_case["checks"]))
        self.assertTrue(all(path.startswith("evidence/20260421T120000+0800-") for path in tmux_case["evidence_files"]))


if __name__ == "__main__":
    unittest.main()
