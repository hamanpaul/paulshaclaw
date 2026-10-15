"""Verify the installed plugin against the public TestPilot Core contract.

This script must be run from outside the checkout after installing the plugin.
It deliberately imports the real core API and treats an unavailable core as an
infrastructure error.
"""

from __future__ import annotations

import importlib.metadata
import sys
from typing import Any


def _error(message: str) -> int:
    print(f"infrastructure error: {message}", file=sys.stderr)
    return 2


def _case_contract(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("id", "<unknown>"))
    readme = case.get("readme")
    if not isinstance(readme, dict) or not isinstance(readme.get("prerequisite_declaration"), dict):
        errors.append(f"{case_id}: missing prerequisite declaration")
    prereq_steps = [
        step
        for step in case.get("steps", [])
        if isinstance(step, dict) and step.get("action") == "install_prerequisites"
    ]
    if len(prereq_steps) != 1 or prereq_steps[0].get("packages_from") != "readme":
        errors.append(f"{case_id}: prerequisite step is not readme-derived")
    topology = case.get("topology")
    dut = topology.get("devices", {}).get("dut", {}) if isinstance(topology, dict) else {}
    if str(dut.get("network", "")).lower() == "none":
        errors.append(f"{case_id}: network none is incompatible with prerequisite installation")
    red_steps = [
        step for step in case.get("steps", [])
        if isinstance(step, dict) and step.get("expected_red_exit_code") is not None
    ]
    for step in red_steps:
        if not isinstance(step.get("expected_red_stderr", ""), str):
            errors.append(f"{case_id}/{step.get('id')}: RED stderr oracle is not a string")
    if case_id == "tc1g-readme-a-venv-install-with-git":
        packages = readme.get("prerequisite_declaration", {}).get("packages", []) if isinstance(readme, dict) else []
        if "git" not in packages:
            errors.append("tc1g-readme-a-venv-install-with-git: git is not declared")
        if not any(
            isinstance(step, dict) and "command -v git" in str(step.get("command", ""))
            for step in case.get("steps", [])
        ):
            errors.append("tc1g-readme-a-venv-install-with-git: git control step is missing")
    comparisons = case.get("image_comparison", [])
    if comparisons:
        comparison_images = set()
        for item in comparisons:
            if not isinstance(item, dict) or not item.get("image_digest"):
                errors.append(f"{case_id}: image comparison is missing a digest")
            elif item.get("image"):
                comparison_images.add(str(item["image"]))
        if not {"ubuntu:22.04", "ubuntu:24.04"}.issubset(comparison_images):
            errors.append(f"{case_id}: image comparison must include Ubuntu 22.04 and 24.04")
    if case_id == "tc1g-readme-a-venv-install-with-git" and dut.get("image") != "ubuntu:22.04":
        errors.append("tc1g-readme-a-venv-install-with-git: primary control image must be Ubuntu 22.04")
    return errors


def main() -> int:
    try:
        from testpilot.api import API_VERSION, PluginBase
    except ModuleNotFoundError as exc:
        return _error(f"testpilot-core public API is unavailable ({exc})")

    try:
        from paulshaclaw_deploy.plugin import CORE_API_VERSION, CORE_VERSION, Plugin
    except ModuleNotFoundError as exc:
        return _error(f"installed plugin or its dependency is unavailable ({exc})")

    try:
        core_version = importlib.metadata.version("testpilot-core")
    except importlib.metadata.PackageNotFoundError:
        return _error("testpilot-core distribution metadata is unavailable")

    if API_VERSION != "1.2" or CORE_API_VERSION != API_VERSION or CORE_VERSION != core_version:
        return _error(
            f"API/version mismatch: API_VERSION={API_VERSION!r}, "
            f"plugin_api={CORE_API_VERSION!r}, plugin_core={CORE_VERSION!r}, "
            f"distribution={core_version!r}"
        )

    plugin = Plugin()
    if not isinstance(plugin, PluginBase):
        return _error("plugin is not an instance of the installed PluginBase")

    checks = plugin.verify_install()
    failed_checks = [message for ok, message in checks if not ok]
    if failed_checks:
        return _error("; ".join(failed_checks))

    cases = plugin.discover_cases()
    if len(cases) != 4:
        return _error(f"installed case discovery returned {len(cases)} cases, expected 4")
    contract_errors = [error for case in cases for error in _case_contract(case)]
    if contract_errors:
        return _error("; ".join(contract_errors))

    print(f"testpilot-core={core_version} api={API_VERSION} plugin={plugin.version} cases={len(cases)}")
    for case in cases:
        print(f"case={case['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
