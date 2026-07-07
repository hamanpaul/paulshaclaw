"""hippo-consumer spec：主 repo 對 paulsha-hippo 的 import 面限定 lib。

daemon 已解耦（#125）；persona/coordinator 僅允許 paulsha_hippo.lib.*。
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_repo_imports_only_hippo_lib():
    offenders = []
    for py in sorted((REPO_ROOT / "paulshaclaw").rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.startswith("paulsha_hippo") and not name.startswith("paulsha_hippo.lib"):
                    offenders.append(f"{py.relative_to(REPO_ROOT)}: {name}")
    assert offenders == []


def test_legacy_memory_and_lifecycle_modules_gone():
    assert not (REPO_ROOT / "paulshaclaw" / "memory").exists()
    assert not (REPO_ROOT / "paulshaclaw" / "lifecycle").exists()
