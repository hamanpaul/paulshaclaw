from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from testpilot.api import TransportBase, StubTransport
from paulshaclaw_deploy.plugin import Plugin


def test_plugin_metadata() -> None:
    plugin = Plugin()
    assert plugin.name == "paulshaclaw_deploy"
    assert plugin.api_version == "1.1"
    assert plugin.version == "0.1.0"
    assert plugin.cases_dir.is_dir()


def test_plugin_discover_cases() -> None:
    plugin = Plugin()
    cases = plugin.discover_cases()
    assert len(cases) == 4
    case_ids = {c.get("id") for c in cases}
    assert case_ids == {
        "tc1-readme-a-venv-install",
        "tc1c-entry-points-intact-no-deps",
        "tc1g-readme-a-venv-install-with-git",
        "tc1p-readme-a-pipx-install",
    }


class FakeTransport(StubTransport):
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.history: list[str] = []
        self.timeouts: list[float] = []
        self.disconnect_calls = 0
        self._container_id = "fake-container"
        self._cleanup_done = False
        self._cleanup_attempted = False
        self._cleanup_error: str | None = None
        self._connected = False

    @property
    def transport_type(self) -> str:
        return "stub"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def container_id(self) -> str | None:
        return self._container_id if self._connected else None

    @property
    def last_container_id(self) -> str:
        return self._container_id

    @property
    def cleanup_done(self) -> bool:
        return self._cleanup_done

    @property
    def cleanup_attempted(self) -> bool:
        return self._cleanup_attempted

    @property
    def cleanup_error(self) -> str | None:
        return self._cleanup_error

    def connect(self, **kwargs: Any) -> None:
        del kwargs
        self._connected = True
        self._cleanup_done = False
        self._cleanup_attempted = False
        self._cleanup_error = None

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._cleanup_attempted = self._connected
        self._cleanup_done = self._connected
        self._connected = False

    def execute(self, command: str, timeout: float = 30.0) -> dict[str, Any]:
        self.history.append(command)
        self.timeouts.append(timeout)
        return self.responses.get(
            command,
            {"returncode": 0, "stdout": "default stdout", "stderr": "", "elapsed": 0.01},
        )


class FakeTopology:
    def __init__(self, transport: TransportBase) -> None:
        self.transport = transport


def test_plugin_step_execution_and_evaluate_pass() -> None:
    plugin = Plugin()
    transport = FakeTransport({
        "cmd1": {"returncode": 0, "stdout": "paulshaclaw 0.2.7", "stderr": "", "elapsed": 0.1},
    })
    topo = FakeTopology(transport)

    step = {"id": "S1", "action": "exec", "target": "dut", "command": "cmd1", "expected_exit_code": 0}
    res = plugin.execute_step({}, step, topo)
    assert res["success"] is True
    assert "paulshaclaw 0.2.7" in res["output"]

    case = {
        "pass_criteria": ["paulshaclaw 0.2.7"],
        "steps": [step],
    }
    eval_res = plugin.evaluate(case, {"steps": {"S1": res}})
    assert eval_res is True


def test_plugin_evaluate_fail() -> None:
    plugin = Plugin()
    step = {"id": "S1", "expected_exit_code": 0}
    res = {
        "success": False,
        "output": "error occurred",
        "captured": {"returncode": 1, "stderr": "Cannot find command 'git'"},
        "timing": 0.1,
    }
    case = {
        "pass_criteria": ["paulshaclaw 0.2.7"],
        "steps": [step],
    }
    eval_res = plugin.evaluate(case, {"steps": {"S1": res}})
    assert eval_res is False


def test_expected_red_oracle_requires_exact_exit_and_stderr() -> None:
    plugin = Plugin()
    step = {
        "id": "S1",
        "expected_exit_code": 0,
        "expected_red_exit_code": 1,
        "expected_red_stderr": "Cannot find command 'git'",
    }
    case = {"steps": [step], "pass_criteria": ["not used for the RED oracle"]}
    matching = {
        "steps": {
            "S1": {
                "output": "Cannot find command 'git'",
                "captured": {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "ERROR: Cannot find command 'git' - do you have 'git' installed?",
                },
            },
        },
    }
    assert plugin.evaluate(case, matching) is False

    wrong_exit = {"steps": {"S1": {"captured": {"returncode": 127, "stderr": "Cannot find command 'git'"}}}}
    assert plugin.evaluate(case, wrong_exit) is False

    wrong_stderr = {"steps": {"S1": {"captured": {"returncode": 1, "stderr": "different error"}}}}
    assert plugin.evaluate(case, wrong_stderr) is False


def test_evaluate_rejects_missing_step_instead_of_defaulting_to_zero() -> None:
    plugin = Plugin()
    case = {
        "steps": [{"id": "S1", "expected_exit_code": 0}],
        "pass_criteria": [],
    }
    assert plugin.evaluate(case, {"steps": {}}) is False


def test_expected_red_live_result_is_reported_as_fail_after_oracle_match() -> None:
    plugin = Plugin()
    transport = FakeTransport({
        "pip install wheel": {
            "returncode": 1,
            "stdout": "",
            "stderr": "Cannot find command 'git'",
            "elapsed": 0.1,
        },
    })
    topology = FakeTopology(transport)
    step = {
        "id": "S1",
        "command": "pip install wheel",
        "expected_exit_code": 0,
        "expected_red_exit_code": 1,
        "expected_red_stderr": "Cannot find command 'git'",
        "timeout_seconds": 17,
    }
    result = plugin.execute_step({}, step, topology)
    assert result["success"] is False
    assert transport.timeouts == [17]
    assert plugin.evaluate({"steps": [step], "pass_criteria": []}, {"steps": {"S1": result}}) is False


def test_readme_parser_only_returns_allow_list_tokens() -> None:
    from paulshaclaw_deploy.plugin import parse_prerequisites

    parsed = parse_prerequisites(
        "# A. Prerequisites\nsudo apt install git python3-venv\n"
        "Do not run evil-package or `rm -rf /`.\n# B. Other\npipx\n"
    )
    assert parsed["source"] == "readme"
    assert parsed["packages"] == ["git", "python3-venv"]


def test_testbed_artifact_mount_and_sha_are_independent(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    wheel = artifact_root / "historical.whl"
    wheel.write_bytes(b"historical artifact")
    checksum = hashlib.sha256(wheel.read_bytes()).hexdigest()
    testbed = tmp_path / "testbed.yaml"
    testbed.write_text(
        yaml.safe_dump({
            "topology": {"default_timeout_seconds": 42},
            "artifacts": {
                "root": "artifacts",
                "historical": {"wheel": {"filename": wheel.name, "sha256": checksum}},
                "candidate": {"wheel": {"path": "", "sha256": ""}},
            },
        }),
        encoding="utf-8",
    )

    plugin = Plugin(testbed_path=testbed)
    mounts = plugin._artifact_mounts({"historical"})
    assert mounts == [(str(wheel.resolve()), "/testpilot/artifacts/historical.whl", "ro")]

    transport = FakeTransport()
    topology = FakeTopology(transport)
    case = {"id": "artifact-check", "artifact_role": "historical"}
    assert plugin.setup_env(case, topology) is True
    assert plugin.verify_env(case, topology) is True
    assert plugin.last_run_metadata["artifacts"]["historical"]["sha256"] == checksum
    plugin.teardown(case, topology)


def test_plugin_failure_is_recorded_and_cleaned_up() -> None:
    plugin = Plugin()
    transport = FakeTransport({
        "false": {
            "returncode": 1,
            "stdout": "",
            "stderr": "expected failure",
            "elapsed": 0.01,
        },
    })
    topology = FakeTopology(transport)
    case = {"id": "failure-case"}
    step = {"id": "S1", "action": "exec", "target": "dut", "command": "false", "expected_exit_code": 0}

    assert plugin.setup_env(case, topology) is True
    result = plugin.execute_step(case, step, topology)
    assert result["success"] is False
    plugin.teardown(case, topology)

    assert transport.disconnect_calls == 1
    report = plugin.case_reports["failure-case"][0]
    assert report["steps"][0]["returncode"] == 1
    assert report["report_complete"] is True


def test_plugin_timeout_is_infrastructure_failure_and_is_cleaned_up() -> None:
    plugin = Plugin()
    transport = FakeTransport({
        "slow": {
            "returncode": -1,
            "stdout": "",
            "stderr": "timed out",
            "elapsed": 17.0,
            "timed_out": True,
            "infrastructure_error": True,
        },
    })
    topology = FakeTopology(transport)
    case = {"id": "timeout-case"}
    step = {"id": "S1", "action": "exec", "target": "dut", "command": "slow", "timeout_seconds": 17}

    assert plugin.setup_env(case, topology) is True
    result = plugin.execute_step(case, step, topology)
    assert result["success"] is False
    assert result["infrastructure_error"] is True
    plugin.teardown(case, topology)

    report = plugin.case_reports["timeout-case"][0]
    assert report["steps"][0]["timed_out"] is True
    assert report["infrastructure_errors"]
    assert report["transport"]["cleanup_attempted"] is True
    assert report["report_complete"] is True


def test_plugin_cleanup_error_is_retained_as_infrastructure_error() -> None:
    class CleanupErrorTransport(FakeTransport):
        @property
        def cleanup_error(self) -> str | None:
            return "cleanup denied"

    plugin = Plugin()
    transport = CleanupErrorTransport()
    topology = FakeTopology(transport)
    case = {"id": "cleanup-error-case"}

    assert plugin.setup_env(case, topology) is True
    plugin.teardown(case, topology)

    report = plugin.case_reports["cleanup-error-case"][0]
    assert report["report_complete"] is True
    assert report["infrastructure_errors"][-1]["reason"] == "cleanup_error"
    assert report["infrastructure_errors"][-1]["detail"] == "cleanup denied"
