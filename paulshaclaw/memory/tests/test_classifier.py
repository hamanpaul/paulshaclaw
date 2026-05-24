import unittest

from paulshaclaw.memory.importer.classifier import classify_session


def make_session(
    *,
    filename: str,
    touched_files: list[str] | None = None,
    prompts: list[str] | None = None,
    referenced_artifacts: list[str] | None = None,
):
    return {
        "session_id": "classifier-case",
        "tool": "copilot-cli",
        "started_at": None,
        "ended_at": "2026-05-24T12:00:00+00:00",
        "cwd": "/repo",
        "repo": "hamanpaul/paulshaclaw",
        "commit": "e300b08",
        "turn_count": 1,
        "user_prompts": prompts or [],
        "assistant_summary": "",
        "touched_files": touched_files or [],
        "referenced_artifacts": referenced_artifacts or [],
        "raw_payload_pointer": filename,
    }


class ClassifierTest(unittest.TestCase):
    def test_classify_session_routes_all_hand_labeled_cases(self):
        cases = [
            (
                "sessions for normal code work",
                "sessions",
                make_session(
                    filename="runtime/queue/session.json",
                    touched_files=["src/router.py"],
                    prompts=["implement routing"],
                ),
            ),
            (
                "sessions for generic markdown edits",
                "sessions",
                make_session(
                    filename="runtime/queue/notes.json",
                    touched_files=["README.md"],
                    prompts=["fix current bug notes"],
                ),
            ),
            (
                "sessions when spec is only a reference",
                "sessions",
                make_session(
                    filename="runtime/queue/default.json",
                    touched_files=["src/main.c"],
                    prompts=["investigate crash"],
                    referenced_artifacts=["docs/spec.md"],
                ),
            ),
            (
                "plans for docs plan artifact",
                "plans",
                make_session(
                    filename="runtime/queue/plan.json",
                    touched_files=["docs/plan.md"],
                    prompts=["update execution notes"],
                ),
            ),
            (
                "plans for plan template path",
                "plans",
                make_session(
                    filename="docs/superpowers/plans/2026-05-24-stage2-memory-importer-mvp.md",
                    touched_files=["src/router.py"],
                    prompts=["follow the checklist"],
                ),
            ),
            (
                "plans for implementation plan prompt",
                "plans",
                make_session(
                    filename="runtime/queue/planning.json",
                    touched_files=["src/router.py"],
                    prompts=["Please draft the implementation plan for task 4"],
                ),
            ),
            (
                "research for research docs",
                "research",
                make_session(
                    filename="runtime/queue/research.json",
                    touched_files=["docs/research/project-routing.md"],
                    prompts=["整理目前限制"],
                ),
            ),
            (
                "research for design docs",
                "research",
                make_session(
                    filename="docs/superpowers/specs/2026-05-24-stage2-memory-importer-mvp-design.md",
                    touched_files=["notes.txt"],
                    prompts=["capture design decisions"],
                ),
            ),
            (
                "research for explicit research prompt",
                "research",
                make_session(
                    filename="runtime/queue/survey.json",
                    touched_files=["notes/research.txt"],
                    prompts=["Research the current importer constraints"],
                ),
            ),
            (
                "sessions when research prompt already touched code",
                "sessions",
                make_session(
                    filename="runtime/queue/research-with-code.json",
                    touched_files=["src/main.py"],
                    prompts=["Research the current importer constraints"],
                ),
            ),
            (
                "reports for review docs",
                "reports",
                make_session(
                    filename="runtime/queue/review.json",
                    touched_files=["reports/review/run-01.md"],
                    prompts=["collect findings"],
                ),
            ),
            (
                "reports for report prompt",
                "reports",
                make_session(
                    filename="runtime/queue/postmortem.json",
                    touched_files=["src/router.py"],
                    prompts=["write the postmortem report"],
                ),
            ),
            (
                "reports for evidence references",
                "reports",
                make_session(
                    filename="runtime/queue/evidence.json",
                    touched_files=["src/router.py"],
                    prompts=["summarize verification"],
                    referenced_artifacts=["reports/verify/run-01/evidence.log"],
                ),
            ),
        ]

        for name, expected, session in cases:
            with self.subTest(name=name):
                self.assertEqual(classify_session(session), expected)


if __name__ == "__main__":
    unittest.main()
