from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def load_ops_companion(testcase: unittest.TestCase):
    try:
        return importlib.import_module("paulshaclaw.security.ops_companion")
    except ModuleNotFoundError as exc:
        testcase.fail(f"ops-companion security module missing: {exc}")


class ApprovalGateTests(unittest.TestCase):
    def test_git_push_requires_explicit_approval(self) -> None:
        mod = load_ops_companion(self)

        decision = mod.ApprovalGate().evaluate("git push origin stage6")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule_id, "git-push")
        self.assertEqual(decision.risk_level, "high")
        self.assertIn("approval", decision.reason.lower())

    def test_ship_command_uses_interactive_approval_flow(self) -> None:
        mod = load_ops_companion(self)

        decision = mod.ApprovalGate().evaluate("/ship stage6 --dry-run")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule_id, "ship-command")
        self.assertEqual(decision.required_action, "interactive-approval")

    def test_package_install_and_remote_ops_share_high_risk_gate(self) -> None:
        mod = load_ops_companion(self)
        gate = mod.ApprovalGate()

        expectations = {
            "pip install safety": "package-install",
            "npm add express": "package-install",
            "pnpm add express": "package-install",
            "yarn add express": "package-install",
            "ssh root@example.org reboot": "remote-operation",
            "deploy production": "deploy-command",
        }

        for command, expected_rule in expectations.items():
            with self.subTest(command=command):
                decision = gate.evaluate(command)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.rule_id, expected_rule)
                self.assertEqual(decision.risk_level, "high")


class RedactionRuleTests(unittest.TestCase):
    def test_redaction_masks_known_secret_shapes_and_tracks_classification(self) -> None:
        mod = load_ops_companion(self)

        payload = (
            "Authorization: Bearer sk-prod-secret-token\n"
            "password=hunter2\n"
            "github=ghp_1234567890abcdefghijklmnopqrstuv"
        )

        result = mod.RedactionEngine().redact(payload)

        self.assertNotIn("sk-prod-secret-token", result.text)
        self.assertNotIn("hunter2", result.text)
        self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuv", result.text)
        self.assertIn("credential", result.classifications)
        self.assertIn("token", result.classifications)
        self.assertIn("bearer-token", result.rule_hits)
        self.assertIn("password-assignment", result.rule_hits)
        self.assertIn("github-token", result.rule_hits)


class AuditTrailTests(unittest.TestCase):
    def test_high_risk_gate_decision_is_recorded_in_audit_trail(self) -> None:
        mod = load_ops_companion(self)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            trail = mod.AppendOnlyAuditTrail(path)
            decision = mod.ApprovalGate().evaluate("/ship stage6 --dry-run")

            entry = mod.record_approval_decision(
                audit_trail=trail,
                actor="operator",
                command="/ship stage6 --dry-run",
                decision=decision,
            )

            self.assertEqual(entry.action, "ship-command.denied")
            self.assertFalse(entry.approved)
            self.assertIn("high-risk", entry.classifications)
            self.assertTrue(trail.verify().ok)

    def test_approved_high_risk_gate_decision_is_recorded_in_audit_trail(self) -> None:
        mod = load_ops_companion(self)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            trail = mod.AppendOnlyAuditTrail(path)
            decision = mod.ApprovalGate().evaluate("/ship stage6 --dry-run", approval_granted=True)

            entry = mod.record_approval_decision(
                audit_trail=trail,
                actor="operator",
                command="/ship stage6 --dry-run",
                decision=decision,
            )

            self.assertEqual(entry.action, "ship-command.approved")
            self.assertTrue(entry.approved)
            self.assertIn("approved", entry.classifications)
            self.assertTrue(trail.verify().ok)

    def test_append_only_audit_trail_links_actor_and_previous_hash(self) -> None:
        mod = load_ops_companion(self)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            trail = mod.AppendOnlyAuditTrail(path)

            first = trail.append(
                actor="operator",
                action="ship.approval.denied",
                target="/ship stage6",
                approved=False,
                classifications=["high-risk"],
            )
            second = trail.append(
                actor="reviewer",
                action="ship.approval.granted",
                target="/ship stage6",
                approved=True,
                classifications=["high-risk", "approved"],
            )
            verification = trail.verify()

            self.assertTrue(verification.ok)
            self.assertEqual(second.previous_hash, first.entry_hash)
            self.assertEqual([entry.actor for entry in trail.read_entries()], ["operator", "reviewer"])

    def test_audit_verification_detects_tampering(self) -> None:
        mod = load_ops_companion(self)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            trail = mod.AppendOnlyAuditTrail(path)
            trail.append(
                actor="operator",
                action="ship.approval.denied",
                target="/ship stage6",
                approved=False,
                classifications=["high-risk"],
            )

            content = path.read_text(encoding="utf-8")
            path.write_text(content.replace("denied", "granted"), encoding="utf-8")

            verification = trail.verify()

            self.assertFalse(verification.ok)
            self.assertEqual(verification.broken_index, 0)
            self.assertIn("hash", verification.reason.lower())


if __name__ == "__main__":
    unittest.main()
