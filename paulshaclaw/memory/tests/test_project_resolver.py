import tempfile
import textwrap
import unittest
from pathlib import Path

from paulshaclaw.memory.importer.config import load_projects_config
from paulshaclaw.memory.importer.project_resolver import resolve_project


REPO_ROOT = Path(__file__).resolve().parents[3]


class ProjectResolverTest(unittest.TestCase):
    def setUp(self):
        self.scratch = REPO_ROOT / ".test-work"
        self.scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.scratch)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        try:
            self.scratch.rmdir()
        except OSError:
            pass

    def write_projects_config(self, text: str) -> Path:
        path = self.root / "projects.yaml"
        path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
        return path

    def test_repo_sample_config_contains_required_projects_and_aliases(self):
        sample = REPO_ROOT / "config" / "agents-projects.sample.yaml"

        config = load_projects_config(sample)

        self.assertIn("paulshaclaw", [project.slug for project in config.projects])
        self.assertIn("obs-auto-moc", [project.slug for project in config.projects])
        self.assertEqual(config.aliases["paulsha"], "paulshaclaw")
        self.assertEqual(config.aliases["obs-moc"], "obs-auto-moc")

    def test_resolve_project_uses_cwd_longest_prefix(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  repo:
                    roots:
                      - /workspace/repo
                  repo-tools:
                    roots:
                      - /workspace/repo-tools
                """
            )
        )

        project = resolve_project(cwd="/workspace/repo-tools/src/module", projects=config)

        self.assertEqual(project, "repo-tools")

    def test_resolve_project_prefers_nested_monorepo_child_over_parent(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  monorepo:
                    roots:
                      - /repo
                  monorepo-web:
                    roots:
                      - /repo/web
                """
            )
        )

        project = resolve_project(cwd="/repo/web/src", projects=config)

        self.assertEqual(project, "monorepo-web")

    def test_resolve_project_falls_back_to_explicit_git_toplevel(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  obs-auto-moc:
                    roots:
                      - /work/custom-claw-tools/obs-auto-moc
                """
            )
        )

        project = resolve_project(
            cwd="/worktrees/stage2-memory-importer-mvp",
            git_toplevel="/work/custom-claw-tools/obs-auto-moc",
            projects=config,
        )

        self.assertEqual(project, "obs-auto-moc")

    def test_resolve_project_matches_remote_url_when_paths_do_not_match(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  paulshaclaw:
                    remotes:
                      - github.com/hamanpaul/paulshaclaw
                """
            )
        )

        project = resolve_project(
            cwd="/unmatched/path",
            remote_url="git@github.com:hamanpaul/paulshaclaw.git",
            projects=config,
        )

        self.assertEqual(project, "paulshaclaw")

    def test_resolve_project_matches_remote_url_variants(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  paulshaclaw:
                    remotes:
                      - github.com/hamanpaul/paulshaclaw
                """
            )
        )

        for remote_url in (
            "https://github.com/hamanpaul/paulshaclaw.git/",
            "GitHub.com/hamanpaul/paulshaclaw",
            "https://token@github.com/hamanpaul/paulshaclaw.git",
            "ssh://git@github.com/hamanpaul/paulshaclaw.git",
            "ssh://git@github.com:22/hamanpaul/paulshaclaw.git",
            "ssh://git@github.com:2222/hamanpaul/paulshaclaw.git",
        ):
            with self.subTest(remote_url=remote_url):
                project = resolve_project(
                    cwd="/unmatched/path",
                    git_toplevel="/another/unmatched/path",
                    remote_url=remote_url,
                    projects=config,
                )

                self.assertEqual(project, "paulshaclaw")

    def test_resolve_project_treats_malformed_remote_port_as_non_match(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  paulshaclaw:
                    remotes:
                      - github.com/hamanpaul/paulshaclaw
                """
            )
        )

        project = resolve_project(
            cwd="/unmatched/path",
            git_toplevel="/another/unmatched/path",
            remote_url="ssh://git@github.com:abc/hamanpaul/paulshaclaw.git",
            projects=config,
        )

        self.assertEqual(project, "_unknown")

    def test_resolve_project_returns_unknown_when_no_rule_matches(self):
        config = load_projects_config(
            self.write_projects_config(
                """
                version: 1
                projects:
                  paulshaclaw:
                    roots:
                      - /repo/paulshaclaw
                    remotes:
                      - github.com/hamanpaul/paulshaclaw
                """
            )
        )

        project = resolve_project(
            cwd="/elsewhere/project",
            git_toplevel="/elsewhere/project",
            remote_url="git@github.com:someone/else.git",
            projects=config,
        )

        self.assertEqual(project, "_unknown")

    def test_alias_collision_warns_and_keeps_first_definition(self):
        config_path = self.write_projects_config(
            """
            version: 1
            projects:
              paulshaclaw:
                aliases: [shared, paulsha]
              obs-auto-moc:
                aliases: [shared, obs-moc]
            """
        )

        with self.assertLogs("paulshaclaw.memory.importer", level="WARNING") as captured:
            config = load_projects_config(config_path)

        self.assertEqual(config.aliases["shared"], "paulshaclaw")
        self.assertEqual(config.aliases["obs-moc"], "obs-auto-moc")
        self.assertIn("shared", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
