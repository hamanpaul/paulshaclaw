from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from paulshaclaw.lifecycle.schema import ARTIFACT_KINDS

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", re.IGNORECASE)


class LlmOutputError(Exception):
    """Raised when agent output is missing, malformed, or schema-invalid."""


@dataclass(frozen=True)
class SliceProposal:
    title: str
    artifact_kind: str
    project: str
    tags: tuple[str, ...]
    body: str
    source_fragment_indices: tuple[int, ...]
    relations: tuple[dict[str, Any], ...]


def _extract_json(raw: str) -> str:
    fenced = _FENCED_JSON_RE.search(raw)
    if fenced:
        return fenced.group(1)

    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise LlmOutputError("no JSON array found in agent output")
    return raw[start:end + 1]


def _require_list(item: dict[str, Any], key: str, index: int) -> list[Any]:
    value = item.get(key)
    if not isinstance(value, list):
        raise LlmOutputError(f"proposal {index} {key} must be a list")
    return value


def _validate_relation(relation: dict[str, Any], index: int, relation_index: int) -> dict[str, Any]:
    relation_type = relation.get("type")
    if relation_type == "relates_to":
        if set(relation) != {"type", "target_title"}:
            raise LlmOutputError(
                f"proposal {index} relation {relation_index} must only contain type and target_title"
            )
        target_title = relation.get("target_title")
        if not isinstance(target_title, str) or not target_title.strip():
            raise LlmOutputError(
                f"proposal {index} relation {relation_index} target_title must be a non-empty string"
            )
    elif relation_type == "mentions":
        if set(relation) != {"type", "entity"}:
            raise LlmOutputError(
                f"proposal {index} relation {relation_index} must only contain type and entity"
            )
        entity = relation.get("entity")
        if not isinstance(entity, str) or not entity.strip():
            raise LlmOutputError(
                f"proposal {index} relation {relation_index} entity must be a non-empty string"
            )
    else:
        raise LlmOutputError(f"proposal {index} relation {relation_index} has invalid type: {relation_type}")
    return dict(relation)


def parse(raw: str, known_projects: list[str]) -> list[SliceProposal]:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise LlmOutputError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise LlmOutputError("agent output must be a JSON array")

    allowed_projects = set(known_projects) | {"_unknown"}
    proposals: list[SliceProposal] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise LlmOutputError(f"proposal {index} is not an object")

        artifact_kind = item.get("artifact_kind")
        if artifact_kind not in ARTIFACT_KINDS:
            raise LlmOutputError(f"proposal {index} has invalid artifact_kind: {artifact_kind}")

        project = item.get("project")
        if project not in allowed_projects:
            raise LlmOutputError(f"proposal {index} has unknown project: {project}")

        body = item.get("body")
        if not isinstance(body, str) or not body.strip():
            raise LlmOutputError(f"proposal {index} has empty body")

        tags = _require_list(item, "tags", index)
        if not all(isinstance(tag, str) for tag in tags):
            raise LlmOutputError(f"proposal {index} tags entries must be strings")

        source_fragment_indices = _require_list(item, "source_fragment_indices", index)
        if not all(isinstance(fragment_index, int) and not isinstance(fragment_index, bool)
                   for fragment_index in source_fragment_indices):
            raise LlmOutputError(f"proposal {index} source_fragment_indices entries must be ints")

        relations = _require_list(item, "relations", index)
        if not all(isinstance(relation, dict) for relation in relations):
            raise LlmOutputError(f"proposal {index} relations entries must be objects")

        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            raise LlmOutputError(f"proposal {index} title must be a non-empty string")

        validated_relations = [
            _validate_relation(relation, index, relation_index)
            for relation_index, relation in enumerate(relations)
        ]

        proposals.append(
            SliceProposal(
                title=title,
                artifact_kind=artifact_kind,
                project=project,
                tags=tuple(tags),
                body=body,
                source_fragment_indices=tuple(source_fragment_indices),
                relations=tuple(validated_relations),
            )
        )
    return proposals
