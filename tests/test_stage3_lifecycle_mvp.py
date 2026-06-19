from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.lifecycle import events, gate, schema, template


def make_artifact_text(
    *,
    phase: str = "research",
    artifact_kind: str = "research",
    body: str = "# Stage3 Artifact\n\nbody\n",
    overrides: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "phase": phase,
        "project": "stage3-demo",
        "slice_id": "11111111-1111-1111-1111-111111111111",
        "artifact_kind": artifact_kind,
        "version": "v1",
        "created_at": "2026-04-21T00:00:00Z",
        "created_by": "operator",
        "source_session": "manual",
        "gate_required": True,
        "checksum": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    if overrides:
        payload.update(overrides)

    frontmatter = "\n".join(f"{key}: {value}" for key, value in payload.items())
    return f"---\n{frontmatter}\n---\n{body}"


class FrontmatterSchemaTests(unittest.TestCase):
    def test_frontmatter_missing_required_field_is_rejected(self) -> None:
        text = make_artifact_text(overrides={"source_session": None})
        result = gate.run_static_gate_check_text(text)

        self.assertFalse(result.ok)
        self.assertIn("source_session", "\n".join(result.errors))

    def test_phase_enum_is_validated(self) -> None:
        text = make_artifact_text(overrides={"phase": "unknown"})
        result = gate.run_static_gate_check_text(text)

        self.assertFalse(result.ok)
        self.assertIn("phase", "\n".join(result.errors))

    def test_checksum_is_validated(self) -> None:
        text = make_artifact_text(overrides={"checksum": "0" * 64})
        result = gate.run_static_gate_check_text(text)

        self.assertFalse(result.ok)
        self.assertIn("checksum", "\n".join(result.errors))

    def test_static_gate_cli_accepts_valid_artifact(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "artifact.md"
            artifact_path.write_text(make_artifact_text(), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "paulshaclaw.lifecycle.gate",
                    "--artifact",
                    str(artifact_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])


class LifecycleTemplateTests(unittest.TestCase):
    def test_lifecycle_template_has_expected_shape(self) -> None:
        state = template.build_lifecycle_template(
            project="stage3-demo",
            current_slice="slice-1",
            workflow_version="0.1.0",
        )

        self.assertEqual(state["project"], "stage3-demo")
        self.assertEqual(state["current_slice"], "slice-1")
        self.assertEqual(state["current_phase"], "research")
        self.assertEqual(state["workflow_version"], "0.1.0")
        self.assertIsNone(state["last_ship"])
        self.assertEqual(state["open_rework"], [])
        self.assertEqual(state["open_rewind"], [])
        self.assertEqual(state["stale_spikes"], [])
        self.assertEqual(set(state["gates"].keys()), set(schema.PHASES))
        for phase in schema.PHASES:
            self.assertEqual(state["gates"][phase]["last_check"], None)
            self.assertEqual(state["gates"][phase]["status"], None)


class EventReplayTests(unittest.TestCase):
    def test_event_stream_rebuilds_current_phase_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            events_path = Path(tmpdir) / "events.jsonl"
            kwargs = {
                "path": events_path,
                "slice_id": "slice-1",
                "phase": "research",
                "project": "stage3-demo",
                "actor": "operator",
            }
            events.append_event(kind="phase.requested", **kwargs)
            events.append_event(kind="phase.artifact_submitted", **kwargs)
            events.append_event(kind="phase.gate_passed", **kwargs)

            state = events.rebuild_phase_state(events_path, slice_id="slice-1")

        self.assertEqual(state.current_phase, "research")
        self.assertEqual(state.phase_status["research"], "passed")
        self.assertIsNone(state.blocked_phase)

    def test_gate_failed_event_blocks_phase(self) -> None:
        with TemporaryDirectory() as tmpdir:
            events_path = Path(tmpdir) / "events.jsonl"
            kwargs = {
                "path": events_path,
                "slice_id": "slice-1",
                "phase": "verify",
                "project": "stage3-demo",
                "actor": "operator",
            }
            events.append_event(kind="phase.requested", **kwargs)
            events.append_event(kind="phase.artifact_submitted", **kwargs)
            events.append_event(kind="phase.gate_failed", **kwargs)

            state = events.rebuild_phase_state(events_path, slice_id="slice-1")

        self.assertEqual(state.current_phase, "blocked:verify")
        self.assertEqual(state.phase_status["verify"], "failed")
        self.assertEqual(state.blocked_phase, "verify")


class GoldenSliceTests(unittest.TestCase):
    def test_golden_slice_full_flow(self) -> None:
        artifact_kind_by_phase = {
            "research": "research",
            "define": "spec",
            "plan": "plan",
            "build": "report",
            "verify": "report",
            "review": "review",
            "ship": "ship-record",
        }

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_path = root / "events.jsonl"
            slice_id = "slice-golden-1"
            for phase in schema.PHASES:
                artifact_path = root / f"{phase}.md"
                artifact_path.write_text(
                    make_artifact_text(phase=phase, artifact_kind=artifact_kind_by_phase[phase]),
                    encoding="utf-8",
                )

                gate_result = gate.run_static_gate_check_file(artifact_path)
                self.assertTrue(gate_result.ok, msg=f"{phase} gate errors: {gate_result.errors}")

                base = {
                    "path": events_path,
                    "slice_id": slice_id,
                    "phase": phase,
                    "project": "stage3-demo",
                    "actor": "operator",
                    "artifact_ref": str(artifact_path),
                }
                events.append_event(kind="phase.requested", **base)
                events.append_event(kind="phase.artifact_submitted", **base)
                events.append_event(kind="phase.gate_passed", **base)

            state = events.rebuild_phase_state(events_path, slice_id=slice_id)

        self.assertEqual(state.current_phase, "ship")
        self.assertIsNone(state.blocked_phase)
        for phase in schema.PHASES:
            self.assertEqual(state.phase_status[phase], "passed")


if __name__ == "__main__":
    unittest.main()
