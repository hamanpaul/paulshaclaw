from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.memory.atomizer import agent_exec
from paulshaclaw.memory.atomizer import llm_promoter, pipeline, slice_frontmatter
from paulshaclaw.memory.atomizer.agent_exec import FakeAgentClient
from paulshaclaw.memory.atomizer.promoter import Promoter
from paulshaclaw.memory.atomizer.splitter import Fragment
from paulshaclaw.memory.ledger import processing, relations

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha body
# Topic B
beta body
"""


def _seed_raw(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(_RAW, encoding="utf-8")
    return raw


_RAW_S2 = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s2
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/y.md
---
# Topic C
gamma body
# Topic D
delta body
"""


def _seed_raw_s2(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s2.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(_RAW_S2, encoding="utf-8")
    return raw


class FailingPromoter(Promoter):
    """Promoter that makes fragment_index==1 of s1 fail validation."""

    def __init__(self, fail_session: str = "s1", fail_index: int = 1):
        self.fail_session = fail_session
        self.fail_index = fail_index

    def promote(
        self, fragments: list[Fragment], config: atomizer_config.AtomizerConfig
    ) -> list[slice_frontmatter.Slice]:
        promoted = []
        for fragment in fragments:
            slice_ = slice_frontmatter.build(fragment, config)
            if (
                fragment.source_session == self.fail_session
                and fragment.fragment_index == self.fail_index
            ):
                bad_fm = dict(slice_.frontmatter)
                del bad_fm["memory_layer"]  # This will fail T4 validation
                slice_ = slice_frontmatter.Slice(
                    slice_id=slice_.slice_id,
                    frontmatter=bad_fm,
                    body=slice_.body,
                )
            promoted.append(slice_)
        return promoted


class BrokenReferencePromoter(Promoter):
    """Promoter that returns one valid slice and one slice without source refs."""

    def promote(
        self, fragments: list[Fragment], config: atomizer_config.AtomizerConfig
    ) -> list[slice_frontmatter.Slice]:
        good = slice_frontmatter.build(fragments[0], config)
        bad = slice_frontmatter.build(fragments[1], config)
        bad_frontmatter = dict(bad.frontmatter)
        bad_frontmatter.pop("fragment_ref", None)
        return [
            good,
            slice_frontmatter.Slice(
                slice_id=bad.slice_id,
                frontmatter=bad_frontmatter,
                body=bad.body,
            ),
        ]


class UnsupportedRelationPromoter(Promoter):
    """Promoter that injects an unsupported semantic relation."""

    def promote(
        self, fragments: list[Fragment], config: atomizer_config.AtomizerConfig
    ) -> list[slice_frontmatter.Slice]:
        base = slice_frontmatter.build(fragments[0], config)
        return [
            slice_frontmatter.Slice(
                slice_id=base.slice_id,
                frontmatter=dict(base.frontmatter),
                body=base.body,
                relations=({"type": "supersedes", "target_title": "x"},),
            )
        ]


class ExplodingPromoter(Promoter):
    """Promoter that raises an unexpected exception for one session."""

    def __init__(self, fail_session: str = "s1") -> None:
        self.fail_session = fail_session

    def promote(
        self, fragments: list[Fragment], config: atomizer_config.AtomizerConfig
    ) -> list[slice_frontmatter.Slice]:
        if fragments and fragments[0].source_session == self.fail_session:
            raise RuntimeError("boom")
        return [slice_frontmatter.build(fragment, config) for fragment in fragments]


class PipelineTests(unittest.TestCase):
    def test_split_pass_creates_fragments_and_archives_raw(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertFalse(raw.exists())  # raw archived out of raw layer
            self.assertTrue(list((root / "archive" / "sessions").rglob("*.md")))
            self.assertTrue(list((root / "knowledge").rglob("*.md")))
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")

    def test_one_to_one_slice_count_matches_fragments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(result["summary"]["slices"], 2)  # two headings -> two slices

    def test_idempotent_second_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            kwargs = dict(config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            pipeline.run(root, **kwargs)
            before = len(list((root / "knowledge").rglob("*.md")))
            result2 = pipeline.run(root, **kwargs)
            self.assertEqual(result2["summary"]["slices"], 0)
            self.assertEqual(len(list((root / "knowledge").rglob("*.md"))), before)

    def test_flow_through_empties_working_layers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])
            self.assertTrue(list((root / "archive" / "fragments").rglob("*.md")))

    def test_identity_pipeline_uses_fragment_ref_fallback_and_records_metadata(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)

            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")

            self.assertEqual(result["summary"]["slices"], 2)
            edges = relations.read_edges(root)
            promoted = [edge for edge in edges if edge["type"] == "promoted_to"]
            self.assertEqual(
                {edge["from"] for edge in promoted},
                {
                    "fragment:claude__s1__000",
                    "fragment:claude__s1__001",
                },
            )
            self.assertEqual(len({edge["to"] for edge in promoted}), 2)
            promoted_event = processing.read_events(root)[-1]
            self.assertEqual(promoted_event["promoter"], "identity")

    def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", dry_run=True)
            self.assertTrue(raw.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertGreater(result["summary"]["slices"], 0)

    def test_dry_run_llm_merge_uses_per_session_promoter(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient(
                    '[{"title":"merged","artifact_kind":"report","project":"paulshaclaw","tags":["x"],'
                    '"body":"merged body","source_fragment_indices":[0,1],"relations":[]}]'
                ),
                skill_text="MERGE-SKILL",
                known_projects=["paulshaclaw"],
            )

            result = pipeline.run(
                root,
                config=cfg,
                config_hash=h,
                now="2026-05-31T03:00:00Z",
                dry_run=True,
                promoter=promoter,
            )

            self.assertTrue(raw.exists())
            self.assertEqual(result["summary"]["slices"], 1)
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])

    def test_unsafe_project_path_is_skipped_without_writing_outside_root(self):
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "memory"
            escaped = parent / "escaped"
            raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(_RAW.replace("project: paulshaclaw", "project: ../../../escaped"),
                           encoding="utf-8")
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")

            self.assertTrue(raw.exists())
            self.assertFalse(escaped.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertGreater(result["summary"]["skipped"], 0)
            self.assertTrue(any("unsafe path field" in w for w in result["warnings"]))

    def test_llm_merge_path_writes_one_slice_and_semantic_edges(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            skill_text = "MERGE-SKILL"
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient(
                    '[{"title":"merged","artifact_kind":"report","project":"paulshaclaw","tags":["alpha"],'
                    '"body":"merged body","source_fragment_indices":[0,1],'
                    '"relations":[{"type":"mentions","entity":"MTK"}]}]'
                ),
                skill_text=skill_text,
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(result["summary"]["slices"], 1)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            written = list((root / "knowledge" / "paulshaclaw").rglob("*.md"))
            self.assertEqual(len(written), 1)

            edges = relations.read_edges(root)
            promoted = [e for e in edges if e["type"] == "promoted_to"]
            mentions = [e for e in edges if e["type"] == "mentions"]
            self.assertEqual(len(promoted), 2)
            self.assertEqual(len(mentions), 1)
            self.assertEqual(mentions[0]["to"], "entity:MTK")
            self.assertEqual({e["from"] for e in promoted}, {"fragment:claude__s1__000", "fragment:claude__s1__001"})
            promoted_event = processing.read_events(root)[-1]
            self.assertEqual(promoted_event["promoter"], "llm")
            self.assertEqual(promoted_event["model"], "fake-llm")
            self.assertEqual(
                promoted_event["skill_hash"],
                hashlib.sha256(skill_text.encode("utf-8")).hexdigest(),
            )

    def test_llm_empty_output_leaves_session_split_without_archiving_fragments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient("[]"),
                skill_text="EMPTY-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertEqual(len(list((root / "inbox" / "_slices").rglob("*.md"))), 2)
            self.assertTrue(any("left in split" in warning for warning in result["warnings"]))

    def test_llm_promotion_archives_unreferenced_fragments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient(
                    '[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body a",'
                    '"source_fragment_indices":[0],"relations":[]}]'
                ),
                skill_text="SUBSET-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(result["summary"]["slices"], 1)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])
            self.assertEqual(len(list((root / "archive" / "fragments").rglob("*.md"))), 2)
            promoted = [e for e in relations.read_edges(root) if e["type"] == "promoted_to"]
            self.assertEqual(len(promoted), 1)
            self.assertEqual(promoted[0]["from"], "fragment:claude__s1__000")

    def test_llm_garbage_leaves_session_split_without_knowledge_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient("not json"),
                skill_text="BROKEN-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            edges = relations.read_edges(root)
            self.assertEqual([e["type"] for e in edges], ["fragment_of", "fragment_of"])
            self.assertTrue(any("left in split" in warning for warning in result["warnings"]))

    def test_llm_relates_to_emits_slice_edge_by_runtime_title(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient(
                    '[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body a",'
                    '"source_fragment_indices":[0],"relations":[]},'
                    '{"title":"beta","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body b",'
                    '"source_fragment_indices":[1],"relations":[{"type":"relates_to","target_title":"alpha"}]}]'
                ),
                skill_text="RELATES-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(result["summary"]["slices"], 2)
            relate_edges = [e for e in relations.read_edges(root) if e["type"] == "relates_to"]
            self.assertEqual(len(relate_edges), 1)
            self.assertTrue(relate_edges[0]["from"].startswith("slice:sl-"))
            self.assertTrue(relate_edges[0]["to"].startswith("slice:sl-"))

    def test_llm_dangling_relates_to_warns_and_promotes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            promoter = llm_promoter.LLMPromoter(
                FakeAgentClient(
                    '[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body a",'
                    '"source_fragment_indices":[0],"relations":[{"type":"relates_to","target_title":"missing"}]}]'
                ),
                skill_text="DANGLING-RELATES-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            self.assertEqual(result["summary"]["slices"], 1)
            relate_edges = [e for e in relations.read_edges(root) if e["type"] == "relates_to"]
            self.assertEqual(relate_edges, [])
            self.assertTrue(any("relates_to target_title" in warning for warning in result["warnings"]))

    def test_promoted_sessions_archive_leftover_fragments_on_resume(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            warnings: list[str] = []
            dry_run_split, _ = pipeline._split_pass(root, cfg, h, "2026-05-31T03:00:00Z", False, warnings)
            self.assertEqual(dry_run_split, 1)
            cached_client = agent_exec.CachingAgentClient(
                FakeAgentClient(
                    '[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body a",'
                    '"source_fragment_indices":[0],"relations":[]}]'
                ),
                root / "runtime" / "cache" / "atomize",
            )
            fragments = [
                pipeline._read_fragment(path)
                for path in sorted((root / "inbox" / "_slices").rglob("*.md"))
            ]
            fragments = [fragment for fragment in fragments if fragment is not None]
            promoter = llm_promoter.LLMPromoter(
                cached_client,
                skill_text="RESUME-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )
            promoter.promote(fragments, cfg)
            self.assertTrue(list((root / "runtime" / "cache" / "atomize").glob("*.json")))
            cache_key = promoter.cache_key_for_fragments(fragments)
            processing.append_state(
                root,
                session_key="claude:s1",
                state="promoted",
                now="2026-05-31T03:01:00Z",
                config_hash=h,
                cache_key=cache_key,
                slices=1,
                promoter="llm",
                model="fake-llm",
                skill_hash="abc123",
            )

            result = pipeline.run(
                root,
                config=cfg,
                config_hash=h,
                now="2026-05-31T03:02:00Z",
                promoter=promoter,
            )

            self.assertEqual(result["summary"]["slices"], 0)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])
            self.assertEqual(len(list((root / "archive" / "fragments").rglob("*.md"))), 2)
            self.assertEqual(list((root / "runtime" / "cache" / "atomize").glob("*.json")), [])

    def test_promoted_session_without_leftover_fragments_still_clears_cache_by_ledger_key(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, h = atomizer_config.load_config(override_path=None)
            cache_key = f"claude:s1__{'a' * 64}"
            cache_path = root / "runtime" / "cache" / "atomize" / f"{cache_key}.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("cached", encoding="utf-8")
            processing.append_state(
                root,
                session_key="claude:s1",
                state="promoted",
                now="2026-05-31T03:01:00Z",
                config_hash=h,
                cache_key=cache_key,
                slices=1,
                promoter="llm",
                model="fake-llm",
                skill_hash="abc123",
            )

            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:02:00Z")

            self.assertEqual(result["summary"]["slices"], 0)
            self.assertFalse(cache_path.exists())

    def test_hostile_ledger_cache_key_does_not_delete_outside_cache_root(self):
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "memory"
            cfg, h = atomizer_config.load_config(override_path=None)
            outside = parent / "outside.json"
            outside.write_text("keep", encoding="utf-8")
            processing.append_state(
                root,
                session_key="claude:s1",
                state="promoted",
                now="2026-05-31T03:01:00Z",
                config_hash=h,
                cache_key="../../outside",
                slices=1,
                promoter="llm",
                model="fake-llm",
                skill_hash="abc123",
            )

            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:02:00Z")

            self.assertEqual(result["summary"]["slices"], 0)
            self.assertTrue(outside.exists())

    def test_successful_llm_promotion_clears_session_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            cached_client = agent_exec.CachingAgentClient(
                FakeAgentClient(
                    '[{"title":"merged","artifact_kind":"report","project":"paulshaclaw","tags":["alpha"],'
                    '"body":"merged body","source_fragment_indices":[0,1],"relations":[]}]'
                ),
                root / "runtime" / "cache" / "atomize",
            )
            promoter = llm_promoter.LLMPromoter(
                cached_client,
                skill_text="CACHE-CLEAR-SKILL",
                known_projects=["paulshaclaw"],
                model="fake-llm",
            )

            result = pipeline.run(
                root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", promoter=promoter
            )

            self.assertEqual(result["summary"]["slices"], 1)
            self.assertEqual(list((root / "runtime" / "cache" / "atomize").glob("*.json")), [])

    def test_unexpected_promoter_error_leaves_session_split_and_allows_later_sessions(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            _seed_raw_s2(root)
            cfg, h = atomizer_config.load_config(override_path=None)

            result = pipeline.run(
                root,
                config=cfg,
                config_hash=h,
                now="2026-05-31T03:00:00Z",
                promoter=ExplodingPromoter(fail_session="s1"),
            )

            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertEqual(processing.state_of(root, "claude:s2"), "promoted")
            self.assertTrue(any("unexpected promoter failure" in warning for warning in result["warnings"]))

    def test_retry_after_phase3_edge_crash_does_not_duplicate_relations(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            warnings: list[str] = []
            pipeline._split_pass(root, cfg, h, "2026-05-31T03:00:00Z", False, warnings)
            original_append = relations.append_edge
            crashed = {"done": False}

            def flaky_append(*args, **kwargs):
                result = original_append(*args, **kwargs)
                if kwargs.get("type") == "promoted_to" and not crashed["done"]:
                    crashed["done"] = True
                    raise OSError("simulated crash after first promoted_to edge")
                return result

            with mock.patch.object(relations, "append_edge", side_effect=flaky_append):
                with self.assertRaises(OSError):
                    pipeline._promote_pass(
                        root,
                        cfg,
                        h,
                        "2026-05-31T03:01:00Z",
                        False,
                        pipeline.IdentityPromoter(),
                        [],
                        {},
                    )

            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:02:00Z")

            self.assertEqual(result["summary"]["slices"], 2)
            edges = relations.read_edges(root)
            edge_triples = [(edge["type"], edge["from"], edge["to"]) for edge in edges]
            self.assertEqual(len(edge_triples), len(set(edge_triples)))

    def test_bad_fragment_references_leave_session_split_without_partial_writes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)

            result = pipeline.run(
                root,
                config=cfg,
                config_hash=h,
                now="2026-05-31T03:00:00Z",
                promoter=BrokenReferencePromoter(),
            )

            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            edges = relations.read_edges(root)
            self.assertEqual([e["type"] for e in edges], ["fragment_of", "fragment_of"])
            self.assertTrue(any("left in split" in warning for warning in result["warnings"]))

    def test_unsupported_semantic_relation_leaves_session_split_without_partial_writes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)

            result = pipeline.run(
                root,
                config=cfg,
                config_hash=h,
                now="2026-05-31T03:00:00Z",
                promoter=UnsupportedRelationPromoter(),
            )

            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            edges = relations.read_edges(root)
            self.assertEqual([e["type"] for e in edges], ["fragment_of", "fragment_of"])
            self.assertTrue(any("unsupported semantic relation type" in w for w in result["warnings"]))

    def test_partial_promote_failure_then_retry(self):
        """
        Regression test for Task 7 review findings:
        1. If fragment N fails validation, fragments 0..N-1 should not have written slices/relations
        2. One bad split session should not block later split sessions
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)  # claude:s1
            _seed_raw_s2(root)  # claude:s2
            cfg, h = atomizer_config.load_config(override_path=None)

            # First run: split+promote with failing promoter that breaks s1 fragment 1
            # This should split both, but only promote s2 (s1 fails validation and stays split)
            kwargs = dict(config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            failing_promoter = FailingPromoter(fail_session="s1", fail_index=1)
            result = pipeline.run(root, **kwargs, promoter=failing_promoter)

            # Verify s1 is still split (failed validation)
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")

            # Verify s2 is promoted (should not be blocked by s1 failure)
            self.assertEqual(processing.state_of(root, "claude:s2"), "promoted")

            # Verify no knowledge slices for s1
            s1_slices = [
                p
                for p in (root / "knowledge" / "paulshaclaw").rglob("*.md")
                if "s1" in p.read_text()
            ]
            self.assertEqual(len(s1_slices), 0, "s1 should not have any knowledge slices after failed promotion")

            # Verify s2 has knowledge slices
            s2_slices = [
                p
                for p in (root / "knowledge" / "paulshaclaw").rglob("*.md")
                if "s2" in p.read_text()
            ]
            self.assertGreater(len(s2_slices), 0, "s2 should have knowledge slices")

            # Verify no promoted_to or distilled_from edges for s1
            edges = relations.read_edges(root)
            s1_promoted_edges = [e for e in edges if e["type"] == "promoted_to" and "__s1__" in e["from"]]
            s1_distilled_edges = [e for e in edges if e["type"] == "distilled_from" and "claude:s1" in e["to"]]
            self.assertEqual(len(s1_promoted_edges), 0, "s1 should not have promoted_to edges after failed promotion")
            self.assertEqual(len(s1_distilled_edges), 0, "s1 should not have distilled_from edges after failed promotion")

            # Verify warning was issued
            self.assertGreater(len(result["warnings"]), 0, "should have warning about failed validation")
            self.assertTrue(
                any("left in split" in w for w in result["warnings"]),
                "warning should mention leaving session in split",
            )

            # Second run: retry with normal promoter (should promote s1 without duplicates)
            result2 = pipeline.run(root, **kwargs)

            # Verify s1 is now promoted
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")

            # Verify no duplicate edges: check that (type, from, to) triples are unique
            edges = relations.read_edges(root)
            edge_triples = [(e["type"], e["from"], e["to"]) for e in edges]
            self.assertEqual(
                len(edge_triples),
                len(set(edge_triples)),
                f"duplicate relation edges detected: {len(edge_triples)} total, {len(set(edge_triples))} unique",
            )


if __name__ == "__main__":
    unittest.main()
