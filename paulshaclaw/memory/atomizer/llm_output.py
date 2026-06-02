from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from paulshaclaw.lifecycle.schema import ARTIFACT_KINDS

_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_JSON_DECODER = json.JSONDecoder()
_EMBEDDED_JSON_PREFIXES = frozenset({":", ",", "[", "{", '"'})
_EMBEDDED_JSON_SUFFIXES = frozenset({":", ",", "]", "}"})
_PROPOSAL_KEYS = frozenset(
    {
        "title",
        "artifact_kind",
        "project",
        "tags",
        "body",
        "source_fragment_indices",
        "relations",
    }
)


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


def _iter_json_arrays(raw: str):
    for fenced in _FENCED_BLOCK_RE.finditer(raw):
        yield from _iter_json_array_candidates(fenced.group(1), offset=fenced.start(1))

    yield from _iter_json_array_candidates(raw, offset=0)


def _iter_json_array_candidates(raw: str, offset: int):
    for start, character in enumerate(raw):
        if character != "[":
            continue
        try:
            candidate, end = _JSON_DECODER.raw_decode(raw, start)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, list) and _is_standalone_json_value(raw, start, end):
            yield candidate, offset + start, offset + end


def _is_standalone_json_value(raw: str, start: int, end: int) -> bool:
    previous = _previous_non_whitespace(raw, start)
    if previous in _EMBEDDED_JSON_PREFIXES:
        return False

    following = _next_non_whitespace(raw, end)
    if following in _EMBEDDED_JSON_SUFFIXES:
        return False

    return True


def _previous_non_whitespace(raw: str, index: int) -> str | None:
    for position in range(index - 1, -1, -1):
        if not raw[position].isspace():
            return raw[position]
    return None


def _next_non_whitespace(raw: str, index: int) -> str | None:
    for position in range(index, len(raw)):
        if not raw[position].isspace():
            return raw[position]
    return None


def _require_field(item: dict[str, Any], key: str, index: int) -> Any:
    if key not in item:
        raise LlmOutputError(f"proposal {index} missing {key}")
    return item[key]


def _require_list(item: dict[str, Any], key: str, index: int) -> list[Any]:
    value = _require_field(item, key, index)
    if not isinstance(value, list):
        raise LlmOutputError(f"proposal {index} {key} must be a list")
    return value


def _require_non_empty_string(item: dict[str, Any], key: str, index: int) -> str:
    value = _require_field(item, key, index)
    if not isinstance(value, str) or not value.strip():
        raise LlmOutputError(f"proposal {index} {key} must be a non-empty string")
    return value


def _require_string_list(item: dict[str, Any], key: str, index: int) -> tuple[str, ...]:
    values = _require_list(item, key, index)
    for value_index, value in enumerate(values):
        if not isinstance(value, str):
            raise LlmOutputError(f"proposal {index} {key}[{value_index}] must be a string")
    return tuple(values)


def _require_int_list(item: dict[str, Any], key: str, index: int) -> tuple[int, ...]:
    values = _require_list(item, key, index)
    for value_index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, int):
            raise LlmOutputError(f"proposal {index} {key}[{value_index}] must be an int")
    return tuple(values)


def _validate_relation(relation: Any, proposal_index: int, relation_index: int) -> dict[str, Any]:
    if not isinstance(relation, dict):
        raise LlmOutputError(f"proposal {proposal_index} relation {relation_index} is not an object")

    relation_type = relation.get("type")
    if relation_type == "relates_to":
        if set(relation) != {"type", "target_title"}:
            raise LlmOutputError(
                f"proposal {proposal_index} relation {relation_index} must match relates_to shape"
            )
        target_title = relation.get("target_title")
        if not isinstance(target_title, str) or not target_title.strip():
            raise LlmOutputError(
                f"proposal {proposal_index} relation {relation_index} target_title must be a non-empty string"
            )
        return relation

    if relation_type == "mentions":
        if set(relation) != {"type", "entity"}:
            raise LlmOutputError(
                f"proposal {proposal_index} relation {relation_index} must match mentions shape"
            )
        entity = relation.get("entity")
        if not isinstance(entity, str) or not entity.strip():
            raise LlmOutputError(
                f"proposal {proposal_index} relation {relation_index} entity must be a non-empty string"
            )
        return relation

    raise LlmOutputError(f"proposal {proposal_index} relation {relation_index} has unsupported type: {relation_type}")


def _parse_proposals(data: Any, known_projects: list[str]) -> list[SliceProposal]:
    if not isinstance(data, list):
        raise LlmOutputError("agent output must be a JSON array")

    allowed_projects = set(known_projects) | {"_unknown"}
    proposals: list[SliceProposal] = []
    seen_titles: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise LlmOutputError(f"proposal {index} is not an object")
        unknown_keys = sorted(set(item) - _PROPOSAL_KEYS)
        if unknown_keys:
            raise LlmOutputError(f"proposal {index} has unknown fields: {', '.join(unknown_keys)}")

        artifact_kind = item.get("artifact_kind")
        if artifact_kind not in ARTIFACT_KINDS:
            raise LlmOutputError(f"proposal {index} has invalid artifact_kind: {artifact_kind}")

        project = item.get("project")
        if project not in allowed_projects:
            raise LlmOutputError(f"proposal {index} has unknown project: {project}")

        title = _require_non_empty_string(item, "title", index)
        if title in seen_titles:
            raise LlmOutputError(f"proposal {index} has duplicate title: {title}")
        seen_titles.add(title)
        body = item.get("body")
        if not isinstance(body, str) or not body.strip():
            raise LlmOutputError(f"proposal {index} has empty body")

        tags = _require_string_list(item, "tags", index)
        source_fragment_indices = _require_int_list(item, "source_fragment_indices", index)
        if not source_fragment_indices:
            raise LlmOutputError(f"proposal {index} source_fragment_indices must not be empty")

        relations = _require_list(item, "relations", index)
        validated_relations = tuple(
            _validate_relation(relation, index, relation_index)
            for relation_index, relation in enumerate(relations)
        )

        proposals.append(
            SliceProposal(
                title=title,
                artifact_kind=artifact_kind,
                project=project,
                tags=tags,
                body=body,
                source_fragment_indices=source_fragment_indices,
                relations=validated_relations,
            )
        )
    return proposals


def parse(raw: str, known_projects: list[str]) -> list[SliceProposal]:
    last_error: LlmOutputError | None = None
    valid_proposals: list[list[SliceProposal]] = []
    seen_spans: set[tuple[int, int]] = set()

    for data, start, end in _iter_json_arrays(raw):
        span = (start, end)
        if span in seen_spans:
            continue
        seen_spans.add(span)
        try:
            valid_proposals.append(_parse_proposals(data, known_projects))
        except LlmOutputError as exc:
            last_error = exc

    if len(valid_proposals) > 1:
        raise LlmOutputError("multiple valid JSON arrays found in agent output")

    if valid_proposals:
        return valid_proposals[0]

    if last_error is not None:
        raise last_error

    raise LlmOutputError("no JSON array found in agent output")
