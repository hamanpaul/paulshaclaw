from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


TEMP_ROOT = Path(__file__).resolve().parent


def temporary_directory():
    return TemporaryDirectory(dir=TEMP_ROOT)


def load_policy(testcase: unittest.TestCase):
    try:
        return importlib.import_module("paulshaclaw.memory.policy")
    except ModuleNotFoundError as exc:
        testcase.fail(f"memory policy module missing: {exc}")


class PolicyLoaderTests(unittest.TestCase):
    def test_load_defaults_lists_required_boundaries_and_rules(self):
        mod = load_policy(self)
        policy = mod.load_default_policy()
        self.assertEqual(policy.policy_version, "0.1.0")
        self.assertIn("external_to_raw", policy.boundaries)
        self.assertIn("raw_to_distilled", policy.boundaries)
        self.assertIn("github_pat", policy.secret_rules)
        self.assertEqual(policy.classification.unknown_project_default, "private")

    def test_local_override_changes_effective_hash_and_disables_session_rule(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text('{"disable_rules_for_session": {"session-a": ["github_pat"]}}', encoding="utf-8")
            base = mod.load_policy(override_path=None)
            overridden = mod.load_policy(override_path=override)
        self.assertNotEqual(base.effective_policy_hash, overridden.effective_policy_hash)
        self.assertIn("github_pat", overridden.disabled_rules_for_session["session-a"])

    def test_override_supports_global_disable_local_regex_and_project_default(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "disable_rules": ["jwt"],
                "append_regex_rules": [{"id": "local_customer", "detector": "regex", "pattern": "ACME-INTERNAL-[0-9]+", "severity": "medium", "description": "local customer marker"}],
                "project_defaults": [{"project": "personal-notes", "level": "private", "reason": "local override"}]
            }), encoding="utf-8")
            policy = mod.load_policy(override_path=override)
        self.assertIn("jwt", policy.disabled_rules)
        self.assertIn("local_customer", policy.secret_rules)
        self.assertEqual(policy.classification.project_defaults["personal-notes"].level, "private")
        self.assertEqual(policy.classification.project_defaults["personal-notes"].reason, "local override")

    def test_project_default_override_keeps_roots_and_remotes(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "project_defaults": [{"project": "client", "level": "private", "reason": "client local", "roots": ["/work/client"], "remotes": ["git@example/client.git"]}]
            }), encoding="utf-8")
            policy = mod.load_policy(override_path=override)
        default = policy.classification.project_defaults["client"]
        self.assertEqual(default.roots, ("/work/client",))
        self.assertEqual(default.remotes, ("git@example/client.git",))

    def test_unsupported_major_version_fails_closed(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            policy_dir = Path(tmp)
            (policy_dir / "secrets.yaml").write_text('{"policy_version":"9.0.0","gitleaks":{"enabled":true},"rules":[]}', encoding="utf-8")
            (policy_dir / "classification.yaml").write_text('{"policy_version":"9.0.0","levels":["public","private","secret"],"unknown_project_default":"private","redaction_hit_default":"private","project_defaults":[]}', encoding="utf-8")
            (policy_dir / "boundaries.yaml").write_text('{"policy_version":"9.0.0","boundaries":[]}', encoding="utf-8")
            with self.assertRaises(mod.PolicyVersionError):
                mod.load_policy(default_dir=policy_dir)

    def test_is_rule_disabled_checks_global_and_session_overrides(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "disable_rules": ["jwt"],
                "disable_rules_for_session": {"session-a": ["github_pat"]}
            }), encoding="utf-8")
            policy = mod.load_policy(override_path=override)
        self.assertTrue(mod.is_rule_disabled(policy, "jwt", "session-a"))
        self.assertTrue(mod.is_rule_disabled(policy, "github_pat", "session-a"))
        self.assertFalse(mod.is_rule_disabled(policy, "github_pat", "session-b"))

    def test_append_regex_rule_cannot_replace_default_rule(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "append_regex_rules": [{"id": "github_pat", "detector": "regex", "pattern": "MALICIOUS", "severity": "low", "description": "bad override"}]
            }), encoding="utf-8")
            with self.assertRaises(mod.PolicyError):
                mod.load_policy(override_path=override)

    def test_project_default_override_can_clear_roots_and_remotes(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "project_defaults": [{"project": "paulshaclaw", "level": "private", "reason": "local clear", "roots": [], "remotes": []}]
            }), encoding="utf-8")
            policy = mod.load_policy(override_path=override)
        default = policy.classification.project_defaults["paulshaclaw"]
        self.assertEqual(default.roots, ())
        self.assertEqual(default.remotes, ())

    def test_append_regex_rule_rejects_invalid_pattern(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "append_regex_rules": [{"id": "local_bad", "detector": "regex", "pattern": "[unclosed", "severity": "medium", "description": "bad regex"}]
            }), encoding="utf-8")
            with self.assertRaises(mod.PolicyError):
                mod.load_policy(override_path=override)

    def test_append_regex_rule_rejects_empty_rule_id(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "append_regex_rules": [{"id": "", "detector": "regex", "pattern": "ACME", "severity": "medium", "description": "empty id"}]
            }), encoding="utf-8")
            with self.assertRaises(mod.PolicyError):
                mod.load_policy(override_path=override)

    def test_append_regex_rule_rejects_non_string_fields(self):
        mod = load_policy(self)
        with temporary_directory() as tmp:
            override = Path(tmp) / "policy.override.yaml"
            override.write_text(json.dumps({
                "append_regex_rules": [{"id": 123, "detector": "regex", "pattern": "ACME", "severity": "medium", "description": "numeric id"}]
            }), encoding="utf-8")
            with self.assertRaises(mod.PolicyError):
                mod.load_policy(override_path=override)
