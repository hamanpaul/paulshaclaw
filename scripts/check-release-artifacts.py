#!/usr/bin/env python3
"""Validate release archives against the source packaging contract.

This module is intentionally stdlib-only so both the local release wrapper and
the GitHub release workflow can invoke the exact same checker before any
artifact is published.
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable


TEMPLATE_MARKER = "paulshaclaw/deploy/templates/"
FORBIDDEN_TEMPLATE_STRINGS = ("__ROOT_DIR__/scripts",)
REQUIRED_PACKAGE_MEMBERS = (
    "paulshaclaw/core/commands.json",
    "paulshaclaw/cockpit/cockpit.tcss",
    "paulshaclaw/launcher/lock.py",
    "paulshaclaw/launcher/services.py",
    "paulshaclaw/launcher/supervisor.py",
    "paulshaclaw/launcher/cli.py",
)
REQUIRED_ENTRY_POINTS = (
    "psc = paulshaclaw.cli:main",
    "paulshaclaw = paulshaclaw.launcher.cli:main",
)


class ArtifactCheckError(RuntimeError):
    """Raised when a release archive violates the source contract."""


def _source_template_paths(source_root: Path) -> set[str]:
    template_root = source_root / "paulshaclaw" / "deploy" / "templates"
    if not template_root.is_dir():
        raise ArtifactCheckError(f"source template directory missing: {template_root}")

    template_files = {
        path.relative_to(template_root).as_posix()
        for path in template_root.rglob("*.tmpl")
        if path.is_file()
    }
    if not template_files:
        raise ArtifactCheckError("source deploy template set is empty")

    empty_directories = [
        path.relative_to(template_root).as_posix() or "."
        for path in template_root.rglob("*")
        if path.is_dir() and not any(child.is_file() for child in path.rglob("*"))
    ]
    if empty_directories:
        raise ArtifactCheckError(
            "source deploy template directory has no template files: "
            + ", ".join(sorted(empty_directories))
        )

    planner_path = source_root / "paulshaclaw" / "deploy" / "planner.py"
    try:
        planner_text = planner_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ArtifactCheckError(f"unable to read planner: {planner_path}: {exc}") from exc
    planner_templates = set(re.findall(r'template_relpath="([^"]+\.tmpl)"', planner_text))
    missing_planner_assets = planner_templates - template_files
    if missing_planner_assets:
        raise ArtifactCheckError(
            "planner references templates absent from source: "
            + ", ".join(sorted(missing_planner_assets))
        )

    for relative in sorted(template_files):
        path = template_root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ArtifactCheckError(f"unable to read source template {relative}: {exc}") from exc
        for forbidden in FORBIDDEN_TEMPLATE_STRINGS:
            if forbidden in text:
                raise ArtifactCheckError(
                    f"source template {relative} contains forbidden string: {forbidden}"
                )
    return template_files


def _template_relative_paths(names: Iterable[str]) -> set[str]:
    paths: set[str] = set()
    for name in names:
        marker_index = name.find(TEMPLATE_MARKER)
        if marker_index < 0:
            continue
        relative = name[marker_index + len(TEMPLATE_MARKER) :]
        if relative and not relative.endswith("/") and relative.endswith(".tmpl"):
            paths.add(relative)
    return paths


def _template_layout_errors(archive_name: str, names: Iterable[str]) -> list[str]:
    """Reject non-template files, empty archive directories, and duplicates."""
    members = [name for name in names if TEMPLATE_MARKER in name]
    errors: list[str] = []
    relative_members: dict[str, list[str]] = {}
    for name in members:
        relative = name[name.find(TEMPLATE_MARKER) + len(TEMPLATE_MARKER) :]
        if not relative:
            continue
        if relative.endswith("/"):
            has_child_file = any(
                other != name
                and other.startswith(name)
                and not other.endswith("/")
                for other in members
            )
            if not has_child_file:
                errors.append(f"{archive_name}: empty template directory: {name}")
            continue
        if not relative.endswith(".tmpl"):
            errors.append(f"{archive_name}: unexpected non-template member: {name}")
            continue
        relative_members.setdefault(relative, []).append(name)

    duplicates = [
        relative for relative, matching in relative_members.items() if len(matching) > 1
    ]
    if duplicates:
        errors.append(
            f"{archive_name}: duplicate template assets: {', '.join(sorted(duplicates))}"
        )
    return errors


def _compare_template_paths(
    *, archive_name: str, actual: set[str], expected: set[str]
) -> list[str]:
    errors: list[str] = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        errors.append(f"{archive_name}: missing template assets: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{archive_name}: unexpected template assets: {', '.join(unexpected)}")
    if not actual:
        errors.append(f"{archive_name}: template asset set is empty")
    return errors


def _check_template_text(archive_name: str, member_name: str, data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{archive_name}: unable to read template {member_name} as UTF-8: {exc}"]
    return [
        f"{archive_name}: template {member_name} contains forbidden string: {forbidden}"
        for forbidden in FORBIDDEN_TEMPLATE_STRINGS
        if forbidden in text
    ]


def _check_required_members(archive_name: str, names: set[str], *, suffix_match: bool) -> list[str]:
    errors: list[str] = []
    for required in REQUIRED_PACKAGE_MEMBERS:
        present = required in names if not suffix_match else any(
            name == required or name.endswith("/" + required) for name in names
        )
        if not present:
            errors.append(f"{archive_name}: missing required member: {required}")
    return errors


def _check_wheel(path: Path, expected_templates: set[str], source_version: str) -> list[str]:
    archive_name = f"wheel {path}"
    if not path.is_file():
        return [f"{archive_name}: file does not exist"]
    try:
        archive = zipfile.ZipFile(path)
    except Exception as exc:
        return [f"{archive_name}: unable to open archive: {exc}"]
    with archive:
        names = archive.namelist()
        name_set = set(names)
        errors = _template_layout_errors(archive_name, names)
        errors.extend(_compare_template_paths(
            archive_name=archive_name,
            actual=_template_relative_paths(names),
            expected=expected_templates,
        ))
        errors.extend(_check_required_members(archive_name, name_set, suffix_match=False))

        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_point_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(metadata_names) != 1:
            errors.append(f"{archive_name}: expected exactly one METADATA member")
        if len(entry_point_names) != 1:
            errors.append(f"{archive_name}: expected exactly one entry_points.txt member")

        if len(metadata_names) == 1:
            try:
                metadata = archive.read(metadata_names[0]).decode("utf-8")
            except Exception as exc:
                errors.append(f"{archive_name}: unable to read METADATA: {exc}")
            else:
                version_line = next(
                    (line for line in metadata.splitlines() if line.startswith("Version:")),
                    "",
                )
                if version_line != f"Version: {source_version}":
                    errors.append(
                        f"{archive_name}: METADATA version does not match VERSION "
                        f"({version_line!r} != 'Version: {source_version}')"
                    )

        if len(entry_point_names) == 1:
            try:
                entry_points = archive.read(entry_point_names[0]).decode("utf-8")
            except Exception as exc:
                errors.append(f"{archive_name}: unable to read entry_points.txt: {exc}")
            else:
                for required in REQUIRED_ENTRY_POINTS:
                    if required not in entry_points:
                        errors.append(f"{archive_name}: missing entry point: {required}")

        for name in names:
            if TEMPLATE_MARKER not in name or not name.endswith(".tmpl"):
                continue
            try:
                data = archive.read(name)
            except Exception as exc:
                errors.append(f"{archive_name}: unable to read template {name}: {exc}")
                continue
            errors.extend(_check_template_text(archive_name, name, data))
        return errors


def _check_sdist(path: Path, expected_templates: set[str], source_version: str) -> list[str]:
    archive_name = f"sdist {path}"
    if not path.is_file():
        return [f"{archive_name}: file does not exist"]
    try:
        archive = tarfile.open(path, "r:gz")
    except Exception as exc:
        return [f"{archive_name}: unable to open archive: {exc}"]
    with archive:
        names = [
            member.name + "/" if member.isdir() and not member.name.endswith("/") else member.name
            for member in archive.getmembers()
        ]
        name_set = set(names)
        errors = _template_layout_errors(archive_name, names)
        errors.extend(_compare_template_paths(
            archive_name=archive_name,
            actual=_template_relative_paths(names),
            expected=expected_templates,
        ))
        errors.extend(_check_required_members(archive_name, name_set, suffix_match=True))

        pyproject_names = [name for name in names if name.endswith("/pyproject.toml") or name == "pyproject.toml"]
        if len(pyproject_names) != 1:
            errors.append(f"{archive_name}: expected exactly one pyproject.toml member")
        if len(pyproject_names) == 1:
            try:
                member = archive.getmember(pyproject_names[0])
                handle = archive.extractfile(member)
                if handle is None:
                    raise OSError("member is not a regular file")
                pyproject = handle.read().decode("utf-8")
            except Exception as exc:
                errors.append(f"{archive_name}: unable to read pyproject.toml: {exc}")
            else:
                if f'version = "{source_version}"' not in pyproject:
                    errors.append(f"{archive_name}: pyproject version does not match VERSION")
                for required in REQUIRED_ENTRY_POINTS:
                    key, value = required.split(" = ", 1)
                    if f'{key} = "{value}"' not in pyproject:
                        errors.append(f"{archive_name}: missing entry point: {required}")

        for name in names:
            if TEMPLATE_MARKER not in name or not name.endswith(".tmpl"):
                continue
            try:
                member = archive.getmember(name)
                handle = archive.extractfile(member)
                if handle is None:
                    raise OSError("member is not a regular file")
                data = handle.read()
            except Exception as exc:
                errors.append(f"{archive_name}: unable to read template {name}: {exc}")
                continue
            errors.extend(_check_template_text(archive_name, name, data))
        return errors


def check_artifacts(*, wheel: Path, sdist: Path, source_root: Path) -> None:
    """Validate wheel and sdist, raising one error containing every failure."""
    try:
        source_version = (source_root / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ArtifactCheckError(f"unable to read source VERSION: {exc}") from exc
    if not source_version:
        raise ArtifactCheckError("source VERSION is empty")

    expected_templates = _source_template_paths(source_root)
    errors = _check_wheel(wheel, expected_templates, source_version)
    errors.extend(_check_sdist(sdist, expected_templates, source_version))
    if errors:
        raise ArtifactCheckError("\n".join(errors))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="checkout containing VERSION, planner, and source templates",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        check_artifacts(
            wheel=args.wheel,
            sdist=args.sdist,
            source_root=args.source_root,
        )
    except ArtifactCheckError as exc:
        for line in str(exc).splitlines():
            print(f"FAIL: {line}", file=sys.stderr)
        return 1
    print("artifact content 檢查通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
