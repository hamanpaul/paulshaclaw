"""Project resolution helpers for Stage 2 memory importer."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from .config import ProjectsConfig, default_projects_path, load_projects_config


def _path_parts(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return PurePosixPath(str(value).replace("\\", "/")).parts


def _best_root_match(candidate: str | None, projects: ProjectsConfig) -> str | None:
    candidate_parts = _path_parts(candidate)
    if not candidate_parts:
        return None
    best_slug: str | None = None
    best_length = -1
    for project in projects.projects:
        for root in project.roots:
            root_parts = _path_parts(root)
            if not root_parts:
                continue
            if len(root_parts) > len(candidate_parts):
                continue
            if candidate_parts[: len(root_parts)] != root_parts:
                continue
            if len(root_parts) > best_length:
                best_slug = project.slug
                best_length = len(root_parts)
    return best_slug


def normalize_remote(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().replace("\\", "/")
    normalized = normalized.rstrip("/")
    normalized = re.sub(r"^[a-z][a-z0-9+.-]*://", "", normalized, flags=re.IGNORECASE)
    if normalized.startswith("git@"):
        normalized = normalized[4:]
    if ":" in normalized and "/" not in normalized.split(":", 1)[0]:
        normalized = normalized.replace(":", "/", 1)
    normalized = normalized.rstrip("/")
    normalized = re.sub(r"\.git$", "", normalized, flags=re.IGNORECASE)
    if normalized.count("/") == 1 and "." not in normalized.split("/", 1)[0]:
        normalized = f"github.com/{normalized}"
    parts = [part for part in normalized.strip("/").split("/") if part]
    if not parts:
        return ""
    parts[0] = parts[0].lower()
    if parts[0] == "github.com":
        parts[1:] = [part.lower() for part in parts[1:]]
    return "/".join(parts)


def resolve_project(
    *,
    cwd: str | None = None,
    git_toplevel: str | None = None,
    remote_url: str | None = None,
    projects: ProjectsConfig | None = None,
    config_path: str | None = None,
    memory_root: str | None = None,
) -> str:
    loaded_projects = projects or load_projects_config(config_path or default_projects_path(memory_root))
    for candidate in (cwd, git_toplevel):
        matched = _best_root_match(candidate, loaded_projects)
        if matched:
            return matched
    normalized_remote = normalize_remote(remote_url)
    if normalized_remote:
        for project in loaded_projects.projects:
            for remote in project.remotes:
                if normalize_remote(remote) == normalized_remote:
                    return project.slug
    return "_unknown"
