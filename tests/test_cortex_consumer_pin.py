from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORTEX_DEPENDENCY_RE = re.compile(
    r"^paulsha-cortex @ git\+https://github\.com/hamanpaul/paulsha-cortex@(?P<sha>[0-9a-f]{40})$"
)


def test_pyproject_pins_paulsha_cortex_to_git_sha() -> None:
    dependencies = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]

    matching_dependency = next(
        (dependency for dependency in dependencies if dependency.startswith("paulsha-cortex @ ")),
        None,
    )

    assert matching_dependency is not None, "pyproject.toml must declare paulsha-cortex as a git+https dependency"
    assert CORTEX_DEPENDENCY_RE.fullmatch(matching_dependency), matching_dependency
