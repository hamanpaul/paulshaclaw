"""TestPilot deployment regression plugin using the real public core API."""

from __future__ import annotations

import hashlib
import importlib.metadata
import logging
import os
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from testpilot.api import API_VERSION as CORE_API_VERSION
from testpilot.api import PluginBase, load_cases_dir

CORE_IMPORT_ERROR = None


try:
    CORE_VERSION = importlib.metadata.version("testpilot-core")
except importlib.metadata.PackageNotFoundError:
    CORE_VERSION = "unavailable"

from paulshaclaw_deploy.docker_transport import DockerTransport, InfrastructureError

log = logging.getLogger(__name__)

ALLOWED_PREREQUISITE_TOKENS = frozenset({
    "ca-certificates",
    "git",
    "pipx",
    "python3",
    "python3-venv",
})
_TOKEN_PATTERNS = tuple(
    (token, re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])"))
    for token in sorted(ALLOWED_PREREQUISITE_TOKENS, key=len, reverse=True)
)


def parse_prerequisites(readme_text: str, section: str = "A") -> dict[str, Any]:
    """Read explicit apt declarations in section A; never execute Markdown."""
    packages: set[str] = set()
    active = False
    level = 0
    fenced = False
    for line in readme_text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)", line) if not fenced else None
        if heading:
            if active and len(heading[1]) <= level:
                break
            if re.match(rf"{re.escape(section)}[.) ]", heading[2]):
                active, level = True, len(heading[1])
            continue
        if not active:
            continue
        declaration = re.fullmatch(r"\s*(?:sudo\s+)?apt(?:-get)?\s+install\s+([a-z0-9 -]+)\s*", line)
        if declaration:
            tokens = declaration[1].split()
            unknown = set(tokens) - ALLOWED_PREREQUISITE_TOKENS - {"-y", "--no-install-recommends"}
            if unknown:
                raise ValueError("unsupported prerequisite package declaration")
            packages.update(set(tokens) & ALLOWED_PREREQUISITE_TOKENS)
    return {"source": "readme" if active else "missing", "section": section, "packages": sorted(packages)}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value or "")


class Plugin(PluginBase):
    """Paulshaclaw deployment and installation regression plugin."""

    api_version = "1.1"

    def __init__(self, testbed_path: Path | str | None = None) -> None:
        super().__init__()
        self._testbed_path_override = Path(testbed_path).expanduser() if testbed_path else None
        self._testbed: dict[str, Any] | None = None
        self._transport: Any = None
        self._active_case: dict[str, Any] | None = None
        self._active_report: dict[str, Any] | None = None
        self._case_reports: dict[str, list[dict[str, Any]]] = {}
        self._prepared_case_ids: set[str] = set()
        self._default_timeout = 300.0
        self._setup_failure: dict[str, Any] | None = None
        self.last_run_metadata: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "paulshaclaw_deploy"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def plugin_root(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def cases_dir(self) -> Path:
        return self.plugin_root / "cases"

    @property
    def testbed_path(self) -> Path:
        configured = os.environ.get("TESTPILOT_TESTBED", "").strip()
        if configured:
            return Path(configured).expanduser()
        if self._testbed_path_override is not None:
            return self._testbed_path_override
        return self.plugin_root / "testbed.yaml.example"

    def _load_testbed(self) -> dict[str, Any]:
        if self._testbed is not None:
            return self._testbed
        path = self.testbed_path
        if not path.is_file():
            raise InfrastructureError(f"Testbed configuration is missing: {path}")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise InfrastructureError(f"Testbed configuration cannot be read: {type(exc).__name__}") from exc
        if not isinstance(raw, dict):
            raise InfrastructureError("Testbed configuration must be a YAML mapping")
        self._testbed = raw
        return raw

    def _validate_case(self, case: dict[str, Any], source: Path | str) -> None:
        required = {"id", "name", "topology", "steps", "pass_criteria"}
        missing = required - set(case)
        if missing:
            raise ValueError(f"{source}: missing case keys: {sorted(missing)}")
        if not isinstance(case.get("steps"), list) or not case["steps"]:
            raise ValueError(f"{source}: steps must be a non-empty list")
        for index, step in enumerate(case["steps"]):
            if not isinstance(step, dict):
                raise ValueError(f"{source}: step {index} must be a mapping")
            if not {"id", "action", "target"}.issubset(step):
                raise ValueError(f"{source}: step {index} misses id/action/target")
            action = str(step.get("action", "")).strip().lower()
            if action == "install_prerequisites" and step.get("packages_from") != "readme":
                raise ValueError(f"{source}: prerequisite steps must use packages_from: readme")
            if action == "install_prerequisites" and "readme" not in case:
                raise ValueError(f"{source}: prerequisite step requires readme metadata")
            red_rc = step.get("expected_red_exit_code")
            red_stderr = step.get("expected_red_stderr")
            if red_rc is not None and _as_int(red_rc) is None:
                raise ValueError(f"{source}: expected_red_exit_code must be an integer")
            if red_stderr is not None and not isinstance(red_stderr, str):
                raise ValueError(f"{source}: expected_red_stderr must be a string")

        topology = _mapping(case.get("topology"))
        devices = _mapping(topology.get("devices"))
        dut = _mapping(devices.get("dut"))
        network = str(dut.get("network", "")).strip().lower()
        commands = [str(step.get("command", "")) for step in case["steps"]]
        if network == "none" and any(
            str(step.get("action", "")).strip().lower() == "install_prerequisites"
            or "pip install" in command
            for step, command in zip(case["steps"], commands)
        ):
            raise ValueError(f"{source}: network none cannot be used for package installation")

        comparison = case.get("image_comparison")
        if comparison is not None:
            if not isinstance(comparison, list) or not comparison:
                raise ValueError(f"{source}: image_comparison must be a non-empty list")
            comparison_images = set()
            for item in comparison:
                if not isinstance(item, dict) or not item.get("image") or not item.get("image_digest"):
                    raise ValueError(f"{source}: image_comparison entries require image and image_digest")
                comparison_images.add(str(item["image"]))
            if not {"ubuntu:22.04", "ubuntu:24.04"}.issubset(comparison_images):
                raise ValueError(f"{source}: image_comparison must include Ubuntu 22.04 and 24.04")

    def discover_cases(self) -> list[dict[str, Any]]:
        """Discover cases through TestPilot's public loader when available."""
        if not self.cases_dir.is_dir():
            return []
        if load_cases_dir is not None:
            return load_cases_dir(self.cases_dir, validator=self._validate_case)

        cases: list[dict[str, Any]] = []
        for yaml_file in sorted(self.cases_dir.glob("*.y*ml")):
            if yaml_file.stem.startswith("_"):
                continue
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._validate_case(data, yaml_file)
                    data.setdefault("id", yaml_file.stem)
                    cases.append(data)
            except (OSError, yaml.YAMLError, ValueError):
                log.exception("failed to load TestPilot case: %s", yaml_file)
        return cases

    def validate_case(self, case: dict[str, Any]) -> None:
        """Apply plugin-specific validation after core schema validation."""
        self._validate_case(case, case.get("id", "<case>"))

    def verify_install(self) -> list[tuple[bool, str]]:
        """Return deterministic install-health checks used by TestPilot CLI."""
        cases = self.discover_cases()
        core_ok = CORE_API_VERSION == "1.2" and CORE_VERSION != "unavailable"
        core_message = (
            f"testpilot-core {CORE_VERSION} public API {CORE_API_VERSION} is importable"
            if core_ok
            else "infrastructure error: testpilot-core public API is unavailable"
        )
        return [
            (core_ok, core_message),
            (len(cases) == 4, "four packaged TestPilot cases are discoverable"),
            (self.testbed_path.is_file(), "testbed template is packaged"),
        ]

    def execution_policy(self, case: dict[str, Any]) -> dict[str, Any]:
        del case
        return {
            "mode": "sequential",
            "max_concurrency": 1,
            "transport": "docker",
            "artifact_mounts": "read-only",
        }

    def report_formats(self) -> list[str]:
        return ["md", "json"]

    @property
    def case_reports(self) -> dict[str, list[dict[str, Any]]]:
        """Return per-attempt reports collected for the current core run."""
        return self._case_reports

    def prepare_run(self, case_ids: Sequence[str] | None) -> Any:
        """Prepare cases and expose immutable run inputs as run artifacts."""
        self._case_reports = {}
        prepared = super().prepare_run(case_ids)
        self._prepared_case_ids = {str(case.get("id", "")) for case in getattr(prepared, "cases", [])}
        artifacts = dict(getattr(prepared, "artifacts", {}) or {})
        artifacts.update({
            "plugin": self.name,
            "plugin_version": self.version,
            "core_version": CORE_VERSION,
            "core_api_version": CORE_API_VERSION,
            "declared_api_version": self.api_version,
            "testbed_template": str(self.testbed_path),
            "case_count": len(getattr(prepared, "cases", [])),
        })
        prepared.artifacts = artifacts
        return prepared

    def _runtime_topology(self, topology: Any) -> dict[str, Any]:
        if isinstance(topology, Mapping):
            return _mapping(topology)
        return _mapping(getattr(topology, "raw", {}))

    def _device_config(self, case: dict[str, Any], topology: Any) -> dict[str, Any]:
        testbed = self._load_testbed()
        merged = _mapping(testbed.get("topology"))
        runtime = self._runtime_topology(topology)
        merged.update(_mapping(runtime.get("topology")))
        case_topology = _mapping(case.get("topology"))
        merged.update({key: value for key, value in case_topology.items() if key != "devices"})
        devices = _mapping(case_topology.get("devices"))
        dut = _mapping(devices.get("dut"))
        merged.update(dut)
        return merged

    def _resolve_path(self, value: Any, *, base: Path, root: Path | None = None) -> Path | None:
        if not isinstance(value, str) or not value.strip():
            return None
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        if root is not None and len(path.parts) == 1:
            return (root / path).resolve()
        return (base / path).resolve()

    def _artifact_specs(self) -> dict[str, dict[str, Any]]:
        testbed = self._load_testbed()
        raw_artifacts = _mapping(testbed.get("artifacts"))
        base = self.testbed_path.parent.resolve()
        root = self._resolve_path(raw_artifacts.get("root", "artifacts"), base=base)

        historical = _mapping(raw_artifacts.get("historical"))
        if not historical:
            historical = _mapping(raw_artifacts.get("v0_2_7_wheel"))
        candidate = _mapping(raw_artifacts.get("candidate"))
        if not candidate:
            candidate = _mapping(raw_artifacts.get("candidate_wheel"))

        def normalize(raw: dict[str, Any], role: str) -> dict[str, Any]:
            wheel = _mapping(raw.get("wheel")) or raw
            filename = wheel.get("filename")
            path_value = wheel.get("path") or filename
            wheel_path = self._resolve_path(
                path_value,
                base=base,
                root=root if role == "historical" and path_value == filename else None,
            )
            checksums_value = raw.get("checksums_file") or wheel.get("checksums_file")
            checksums_path = self._resolve_path(
                checksums_value,
                base=base,
                root=root if role == "historical" else None,
            )
            return {
                "role": role,
                "filename": str(filename or (wheel_path.name if wheel_path else "")),
                "path": wheel_path,
                "sha256": str(wheel.get("sha256") or "").strip(),
                "checksums_file": checksums_path,
                "readme_revision": str(raw.get("readme_revision") or wheel.get("readme_revision") or ""),
                "root": root,
            }

        return {
            "historical": normalize(historical, "historical"),
            "candidate": normalize(candidate, "candidate"),
        }

    def _artifact_mounts(self, roles: set[str]) -> list[tuple[str, str, str]]:
        mounts: list[tuple[str, str, str]] = []
        for role in sorted(roles):
            spec = self._artifact_specs().get(role, {})
            wheel_path = spec.get("path")
            checksums_path = spec.get("checksums_file")
            container_dir = "/testpilot/candidate" if role == "candidate" else "/testpilot/artifacts"
            host_files = [item for item in (wheel_path, checksums_path) if isinstance(item, Path) and item.is_file()]
            for host_file in host_files:
                entry = (str(host_file), f"{container_dir}/{host_file.name}", "ro")
                if entry not in mounts:
                    mounts.append(entry)
        return mounts

    def _artifact_catalog(self) -> dict[str, dict[str, Any]]:
        """Return both artifact roles without exposing one role through the other."""
        catalog: dict[str, dict[str, Any]] = {}
        for role, spec in self._artifact_specs().items():
            path = spec.get("path")
            checksums = spec.get("checksums_file")
            catalog[role] = {
                "filename": spec.get("filename", ""),
                "path": Path(path).name if isinstance(path, Path) else "",
                "sha256": spec.get("sha256", ""),
                "checksums_file": Path(checksums).name if isinstance(checksums, Path) else "",
                "readme_revision": spec.get("readme_revision", ""),
                "mount": "/testpilot/candidate" if role == "candidate" else "/testpilot/artifacts",
            }
        return catalog

    def _readme_metadata(self, case: dict[str, Any]) -> dict[str, Any]:
        readme = dict(_mapping(case.get("readme")))
        readme.update(_mapping(self._load_testbed().get("readme")))
        revision = str(readme.get("revision") or "ddc4ab74f77e680ecb621a2ba511af5e4041828a")
        path = self._resolve_path(readme.get("path"), base=self.testbed_path.parent.resolve())
        if path is None:
            path = self.plugin_root / "fixtures/README-v0.2.7.txt"
        if not path.is_file():
            raise InfrastructureError("README input missing")
        digest = self._sha256(path)
        expected = readme.get("sha256")
        if expected and digest != expected:
            raise InfrastructureError("README sha256 mismatch")
        parsed = parse_prerequisites(path.read_text(encoding="utf-8"))
        packages = {"python3", "python3-venv"}
        case_id = str(case.get("id", ""))
        if not case_id.startswith("tc1c-"):
            packages.update(parsed["packages"])
        if case_id.startswith("tc1g-"):
            packages.add("git")
        if case_id.startswith("tc1p-"):
            packages.add("pipx")
        return {**parsed, "revision": revision, "sha256": digest, "path": path.name,
                "declared_packages": parsed["packages"], "packages": sorted(packages)}

    def _case_artifact_role(self, case: dict[str, Any]) -> str | None:
        explicit = case.get("artifact_role")
        if isinstance(explicit, str) and explicit in {"historical", "candidate"}:
            return explicit
        artifact = _mapping(case.get("artifacts"))
        role = artifact.get("role")
        return role if role in {"historical", "candidate"} else None

    def _record_transport(self, transport: Any) -> dict[str, Any]:
        return {
            "transport": getattr(transport, "transport_type", type(transport).__name__),
            "container_id": getattr(transport, "container_id", None),
            "last_container_id": getattr(transport, "last_container_id", None),
            "image": getattr(transport, "image", None),
            "image_digest": getattr(transport, "image_digest", None),
            "uid": getattr(transport, "uid", None),
            "user": getattr(transport, "user", None),
            "network": getattr(transport, "network", None),
            "cleanup": getattr(transport, "cleanup_done", None),
            "cleanup_attempted": getattr(transport, "cleanup_attempted", None),
            "cleanup_error": getattr(transport, "cleanup_error", None),
        }

    def setup_env(self, case: dict[str, Any], topology: Any) -> bool:
        """Create a transport and mount only explicitly configured artifacts."""
        self._active_case = case
        self._setup_failure = None
        case_id = str(case.get("id", ""))
        self._active_report = {
            "case_id": case_id,
            "attempt": _as_int(case.get("_attempt_index")) or 1,
            "core_version": CORE_VERSION,
            "core_api_version": CORE_API_VERSION,
            "readme": self._readme_metadata(case),
            "artifacts": self._artifact_catalog(),
            "transport": {},
            "steps": [],
            "infrastructure_errors": [],
            "report_complete": False,
        }
        self.last_run_metadata = {
            "case_id": case_id,
            "core_version": CORE_VERSION,
            "core_api_version": CORE_API_VERSION,
            "readme": self._readme_metadata(case),
            "artifacts": self._artifact_catalog(),
        }

        supplied_transport = getattr(topology, "transport", None)
        if supplied_transport is None and isinstance(topology, Mapping):
            supplied_transport = topology.get("transport")
        if supplied_transport is not None:
            self._transport = supplied_transport
            try:
                if not supplied_transport.is_connected:
                    supplied_transport.connect()
                self.last_run_metadata["transport"] = self._record_transport(supplied_transport)
                self._active_report["transport"] = self._record_transport(supplied_transport)
                return True
            except (InfrastructureError, OSError, RuntimeError) as exc:
                self._setup_failure = {
                    "category": "infrastructure",
                    "reason": type(exc).__name__,
                }
                self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
                self._active_report["transport"] = self._record_transport(supplied_transport)
                return False

        try:
            device = self._device_config(case, topology)
            role = self._case_artifact_role(case)
            roles = {role} if role else set()
            volumes = self._artifact_mounts(roles)
            image_digest = str(device.get("image_digest") or "").strip()
            if not image_digest:
                raise ValueError("image_digest is required for Docker testbeds")
            uid = _as_int(device.get("uid"))
            transport = DockerTransport(
                image=str(device.get("image") or device.get("base_image") or "ubuntu:24.04"),
                image_digest=image_digest,
                user=str(device.get("user") or "testuser") or None,
                uid=uid,
                network=str(device.get("network") or "") or None,
                volumes=volumes,
            )
            self._transport = transport
            transport.connect()
            self._default_timeout = _as_float(
                device.get("default_timeout_seconds"),
                _as_float(_mapping(self._load_testbed().get("topology")).get("default_timeout_seconds"), 300.0),
            )
            self.last_run_metadata["transport"] = self._record_transport(transport)
            self._active_report["transport"] = self._record_transport(transport)
            case["_testbed"] = str(self.testbed_path)
            case["_artifact_mounts"] = list(volumes)
            return True
        except InfrastructureError as exc:
            self._setup_failure = {
                "category": "infrastructure",
                "reason": str(exc).split(":", 1)[0],
            }
            self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
            if self._transport is not None:
                self._active_report["transport"] = self._record_transport(self._transport)
            return False
        except (OSError, ValueError, yaml.YAMLError) as exc:
            self._setup_failure = {
                "category": "configuration",
                "reason": type(exc).__name__,
            }
            self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
            if self._transport is not None:
                self._active_report["transport"] = self._record_transport(self._transport)
            return False

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify_env(self, case: dict[str, Any], topology: Any) -> bool:
        """Validate transport, artifact identity and readme provenance."""
        del topology
        if self._setup_failure is not None:
            self.last_run_metadata["environment"] = dict(self._setup_failure)
            return False
        if self._transport is None or not getattr(self._transport, "is_connected", False):
            self._setup_failure = {"category": "infrastructure", "reason": "transport_not_connected"}
            self.last_run_metadata["environment"] = dict(self._setup_failure)
            if self._active_report is not None:
                self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
            return False

        role = self._case_artifact_role(case)
        if role:
            spec = self._artifact_specs()[role]
            path = spec.get("path")
            if not isinstance(path, Path) or not path.is_file():
                self._setup_failure = {"category": "infrastructure", "reason": "artifact_missing"}
                self.last_run_metadata["environment"] = dict(self._setup_failure)
                if self._active_report is not None:
                    self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
                return False
            expected_hash = str(spec.get("sha256") or "")
            if expected_hash and self._sha256(path).lower() != expected_hash.lower():
                self._setup_failure = {"category": "configuration", "reason": "artifact_sha256_mismatch"}
                self.last_run_metadata["environment"] = dict(self._setup_failure)
                if self._active_report is not None:
                    self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
                return False
            checksums = spec.get("checksums_file")
            if checksums is not None and not isinstance(checksums, Path):
                self._setup_failure = {"category": "configuration", "reason": "checksum_path_invalid"}
                self.last_run_metadata["environment"] = dict(self._setup_failure)
                if self._active_report is not None:
                    self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
                return False
            if isinstance(checksums, Path) and not checksums.is_file():
                self._setup_failure = {"category": "infrastructure", "reason": "checksum_file_missing"}
                self.last_run_metadata["environment"] = dict(self._setup_failure)
                if self._active_report is not None:
                    self._active_report["infrastructure_errors"].append(dict(self._setup_failure))
                return False
            self.last_run_metadata.setdefault("artifacts", {})[role] = {
                "path": str(path),
                "sha256": expected_hash,
                "readme_revision": spec.get("readme_revision", ""),
            }

        case["_readme"] = self.last_run_metadata.get("readme", {})
        return True

    def _transport_for(self, topology: Any) -> Any:
        transport = getattr(topology, "transport", None)
        if transport is None and isinstance(topology, Mapping):
            transport = topology.get("transport")
        return transport or self._transport

    def _step_timeout(self, step: dict[str, Any]) -> float:
        return _as_float(
            step.get("timeout_seconds", step.get("timeout")),
            self._default_timeout,
        )

    def _step_command(self, case: dict[str, Any], step: dict[str, Any]) -> str:
        if str(step.get("action", "")).strip().lower() == "install_prerequisites":
            metadata = self._readme_metadata(case)
            packages = [
                package
                for package in metadata.get("packages", [])
                if package in ALLOWED_PREREQUISITE_TOKENS
            ]
            if not packages:
                return "false  # no allow-listed prerequisites declared"
            return (
                "export DEBIAN_FRONTEND=noninteractive; "
                "apt-get update && apt-get install -y --no-install-recommends "
                f"{shlex.join(sorted(set(packages)))}"
            )
        command = step.get("command")
        if isinstance(command, list):
            return "\n".join(str(item) for item in command)
        if isinstance(command, str) and command.strip():
            return command
        return f"{step.get('action', '')} {step.get('target', '')}".strip()

    def execute_step(
        self,
        case: dict[str, Any],
        step: dict[str, Any],
        topology: Any,
    ) -> dict[str, Any]:
        """Execute one step and apply its exit/stderr oracle immediately."""
        transport = self._transport_for(topology)
        timeout = self._step_timeout(step)
        command = self._step_command(case, step)
        try:
            if transport is None:
                device = self._device_config(case, topology)
                role = self._case_artifact_role(case)
                image_digest = str(device.get("image_digest") or "").strip()
                if not image_digest:
                    raise InfrastructureError("image_digest is required for Docker testbeds")
                transport = DockerTransport(
                    image=str(device.get("image") or device.get("base_image") or "ubuntu:24.04"),
                    image_digest=image_digest,
                    user=str(device.get("user") or "testuser") or None,
                    uid=_as_int(device.get("uid")),
                    network=str(device.get("network") or "") or None,
                    volumes=self._artifact_mounts({role} if role else set()),
                )
                transport.connect()
                self._transport = transport

            run_as = step.get("run_as")
            if run_as is not None and callable(getattr(transport, "execute_as", None)):
                raw = dict(transport.execute_as(command, user=str(run_as), timeout=timeout))
            else:
                raw = dict(transport.execute(command, timeout=timeout))
        except InfrastructureError as exc:
            raw = {
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
                "elapsed": 0.0,
                "infrastructure_error": True,
            }
        except (OSError, RuntimeError) as exc:
            raw = {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Transport error: {type(exc).__name__}",
                "elapsed": 0.0,
                "infrastructure_error": True,
            }

        stdout = _as_text(raw.get("stdout"))
        stderr = _as_text(raw.get("stderr"))
        actual_rc = raw.get("returncode")
        expected_red_rc = _as_int(step.get("expected_red_exit_code"))
        expected_red_stderr = _as_text(step.get("expected_red_stderr")).strip()
        infrastructure = bool(raw.get("infrastructure_error") or raw.get("timed_out"))
        red_match = False
        if expected_red_rc is not None:
            red_match = (not infrastructure and actual_rc == expected_red_rc
                         and (not expected_red_stderr or expected_red_stderr in stderr))
        expected_rc = _as_int(step.get("expected_exit_code"))
        success = not infrastructure and actual_rc == (0 if expected_rc is None else expected_rc)
        if "stdout_equals" in step:
            success = success and stdout.rstrip("\n") == step["stdout_equals"]
        if "output_contains" in step:
            success = success and step["output_contains"] in stdout + stderr

        captured = dict(raw)
        captured.update({
            "command": command,
            "timeout": timeout,
            "observed": True,
            "red_oracle_matched": red_match,
            "infrastructure_error": infrastructure,
        })
        output = stdout
        if stderr:
            output = f"{output}\n{stderr}" if output else stderr
        result = {
            "success": bool(success),
            "output": output,
            "captured": captured,
            "timing": raw.get("elapsed", 0.0),
            "infrastructure_error": infrastructure,
            "command": command,
        }
        if self._active_report is not None:
            self._active_report["steps"].append({
                "id": str(step.get("id", "")),
                "action": str(step.get("action", "")),
                "run_as": str(step.get("run_as")) if step.get("run_as") is not None else None,
                "command": command,
                "timeout": timeout,
                "expected_exit_code": _as_int(step.get("expected_exit_code")),
                "expected_red_exit_code": expected_red_rc,
                "expected_red_stderr": expected_red_stderr,
                "success": bool(success),
                "red_oracle_matched": red_match,
                "infrastructure_error": infrastructure,
                "returncode": raw.get("returncode"),
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": bool(raw.get("timed_out")),
                "elapsed": raw.get("elapsed", 0.0),
            })
            if infrastructure:
                self._active_report["infrastructure_errors"].append({
                    "category": "infrastructure",
                    "reason": "step_timeout" if raw.get("timed_out") else "transport_error",
                    "step_id": str(step.get("id", "")),
                })
        return result

    @staticmethod
    def _observed_red_match(step: dict[str, Any], result: dict[str, Any]) -> bool:
        captured = _mapping(result.get("captured"))
        actual_rc = captured.get("returncode")
        if actual_rc is None:
            return False
        if captured.get("infrastructure_error") or captured.get("timed_out"):
            return False
        expected_rc = _as_int(step.get("expected_red_exit_code"))
        if expected_rc is None or actual_rc != expected_rc:
            return False
        expected_stderr = _as_text(step.get("expected_red_stderr")).strip()
        stderr = _as_text(captured.get("stderr"))
        output = _as_text(result.get("output"))
        return not expected_stderr or expected_stderr in stderr or expected_stderr in output

    def evaluate(self, case: dict[str, Any], results: dict[str, Any]) -> bool:
        """The raw verdict always tests the successful installation contract."""
        observed = results.get("steps", {})
        outputs = []
        for step in case.get("steps", []):
            result = observed.get(step["id"])
            if not isinstance(result, dict):
                return False
            captured = result.get("captured", {})
            if captured.get("timed_out") or captured.get("infrastructure_error"):
                return False
            if captured.get("returncode") != step.get("expected_exit_code", 0):
                return False
            stdout, stderr = str(captured.get("stdout", "")), str(captured.get("stderr", ""))
            if "stdout_equals" in step and stdout.rstrip("\n") != step["stdout_equals"]:
                return False
            if "output_contains" in step and step["output_contains"] not in stdout + stderr:
                return False
            outputs.append(stdout + stderr)
        return all(str(item) in "\n".join(outputs) for item in case.get("pass_criteria", []))

    def run_pipeline(self, case: dict[str, Any], topology: Any) -> dict[str, Any]:
        """Collect all diagnostics even after installation fails; always clean up."""
        self.last_run_metadata = {}
        self._active_report = None
        results: dict[str, Any] = {}
        verdict = False
        comment = ""
        try:
            if self.setup_env(case, topology) and self.verify_env(case, topology):
                for step in case["steps"]:
                    results[step["id"]] = self.execute_step(case, step, topology)
                verdict = self.evaluate(case, {"steps": results})
            else:
                comment = "environment validation failed"
        except Exception as exc:
            comment = f"infrastructure error: {exc}"
            if self._active_report is not None:
                self._active_report["infrastructure_errors"].append({"reason": comment})
        finally:
            self.teardown(case, topology)
        report = self.last_run_metadata.get("case_report", {})
        if report.get("infrastructure_errors"):
            verdict = False
        return {"verdict": verdict, "comment": comment, "steps": results}

    def create_runner(self) -> Any:
        from paulshaclaw_deploy.runner import DeployRunner
        return DeployRunner(self)

    def teardown(self, case: dict[str, Any], topology: Any) -> None:
        """Always attempt cleanup and retain its result in run metadata."""
        transport = self._transport_for(topology)
        cleanup_exception: Exception | None = None
        if transport is not None and hasattr(transport, "disconnect"):
            try:
                transport.disconnect()
                if getattr(transport, "container_id", None):
                    transport.disconnect()
            except Exception as exc:  # pragma: no cover - defensive transport boundary
                cleanup_exception = exc
            finally:
                self.last_run_metadata["transport"] = self._record_transport(transport)
        if self._active_report is not None:
            self._active_report["transport"] = self._record_transport(transport) if transport is not None else {}
            if cleanup_exception is not None:
                self._active_report["infrastructure_errors"].append({
                    "category": "infrastructure",
                    "reason": "cleanup_error",
                    "error_type": type(cleanup_exception).__name__,
                })
            transport_report = self._active_report["transport"]
            if isinstance(transport_report, dict) and transport_report.get("cleanup_error"):
                self._active_report["infrastructure_errors"].append({
                    "category": "infrastructure",
                    "reason": "cleanup_error",
                    "detail": transport_report["cleanup_error"],
                })
            self._active_report["report_complete"] = bool(
                isinstance(transport_report, dict)
                and "last_container_id" in transport_report
                and "cleanup_attempted" in transport_report
                and "cleanup_error" in transport_report
                and isinstance(self._active_report.get("steps"), list)
            )
            case_id = str(self._active_report.get("case_id") or case.get("id", ""))
            self._case_reports.setdefault(case_id, []).append(dict(self._active_report))
            self.last_run_metadata["case_report"] = dict(self._active_report)
        self._transport = None
        self._active_case = None
        self._active_report = None
