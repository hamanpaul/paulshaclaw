from __future__ import annotations

from collections.abc import Callable, Sequence

from paulshaclaw.memory.atomizer.agent_exec import AgentClient
from paulshaclaw.memory.atomizer.config import AtomizerConfig, load_config
from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
from paulshaclaw.memory.atomizer.slice_frontmatter import Slice
from paulshaclaw.memory.atomizer.splitter import Fragment


def make_atomize_rollout(
    agent_client: AgentClient,
    known_projects: Sequence[str],
    *,
    config: AtomizerConfig | None = None,
) -> Callable[[str, list[Fragment]], list[Slice]]:
    cfg = config
    if cfg is None:
        cfg, _ = load_config()

    projects = list(known_projects)

    def rollout(skill_text: str, fragments: list[Fragment]) -> list[Slice]:
        if not fragments:
            return []

        promoter = LLMPromoter(
            agent_client,
            skill_text,
            projects,
            model=cfg.agent_exec_model,
        )
        return promoter.promote(fragments, cfg)

    return rollout
