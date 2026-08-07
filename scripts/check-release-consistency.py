#!/usr/bin/env python3
"""Release 一致性 gate。

比對四個版本來源，任一不一致即以非零退出（fail-closed）：

1. ``VERSION`` 檔
2. ``pyproject.toml`` 的 ``[project].version``
3. （release 模式）Git tag ``vX.Y.Z``，且該 tag 必須指向 HEAD
4. （release 模式）``CHANGELOG.md`` 存在 ``## [X.Y.Z]`` release section

不帶 ``--tag`` 時只做 (1)+(2) 一致性檢查（適用一般 CI／本機 preflight）；
帶 ``--tag vX.Y.Z`` 時進入完整 release gate，用於 release workflow cut 前驗證。

另外提供 ``--extract-notes <X.Y.Z>`` 輸出 CHANGELOG 對應 section body，
供 release workflow 產生 release notes（找不到該 section 時 fail）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

_CHANGELOG_SECTION_RE = re.compile(
    r"^##\s*\[(?P<ver>[^\]]+)\]", re.MULTILINE
)


def read_version_file(repo_root: Path) -> str:
    return (repo_root / "VERSION").read_text(encoding="utf-8").strip()


def read_pyproject_version(repo_root: Path) -> str:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def changelog_release_versions(repo_root: Path) -> list[str]:
    text = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    return [m.group("ver") for m in _CHANGELOG_SECTION_RE.finditer(text)]


def extract_changelog_section(repo_root: Path, version: str) -> str:
    """回傳 ``## [version]`` section 的 body（到下一個 ``## `` 為止）。

    找不到該 section 時拋 ``LookupError``。
    """
    text = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    matches = list(_CHANGELOG_SECTION_RE.finditer(text))
    target = next((m for m in matches if m.group("ver") == version), None)
    if target is None:
        raise LookupError(f"CHANGELOG.md 找不到 ## [{version}] section")
    start = target.end()
    nxt = next((m for m in matches if m.start() > target.start()), None)
    end = nxt.start() if nxt is not None else len(text)
    return text[start:end].strip()


def tag_points_at_head(repo_root: Path, tag: str) -> bool:
    """tag 指向的 commit 是否等於 HEAD。"""
    # `^{commit}` 是必要的：annotated / signed tag 的 `refs/tags/<tag>` 解析出來
    # 是 tag object 的 SHA 而非 commit，直接比對會把正確的 release tag 判成不一致。
    tag_sha = subprocess.run(
        ["git", "rev-parse", f"refs/tags/{tag}^{{commit}}"],
        capture_output=True,
        cwd=repo_root,
        text=True,
        check=False,
    )
    if tag_sha.returncode != 0:
        return False
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        cwd=repo_root,
        text=True,
        check=True,
    ).stdout.strip()
    return tag_sha.stdout.strip() == head_sha


def check_consistency(repo_root: Path, tag: str | None) -> list[str]:
    """回傳不一致原因清單；空清單代表通過。"""
    offenders: list[str] = []
    v_file = read_version_file(repo_root)
    v_pyproject = read_pyproject_version(repo_root)
    if v_file != v_pyproject:
        offenders.append(f"VERSION({v_file}) != pyproject.toml({v_pyproject})")

    if tag is None:
        return offenders

    tag_version = re.sub(r"^v", "", tag)
    if not re.fullmatch(r"\d+\.\d+\.\d+", tag_version):
        offenders.append(f"tag {tag} 不符合 vX.Y.Z SemVer 格式")
        return offenders
    if v_file != tag_version:
        offenders.append(f"VERSION({v_file}) != tag({tag_version})")
    if v_pyproject != tag_version:
        offenders.append(f"pyproject.toml({v_pyproject}) != tag({tag_version})")
    if not tag_points_at_head(repo_root, tag):
        offenders.append(f"tag {tag} 未指向 HEAD（source revision 不一致）")
    if tag_version not in changelog_release_versions(repo_root):
        offenders.append(
            f"CHANGELOG.md 缺少 ## [{tag_version}] release section"
        )
    return offenders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", help="release tag，例如 vX.Y.Z；不給則只做 VERSION/pyproject 一致性")
    parser.add_argument(
        "--extract-notes",
        metavar="VERSION",
        help="只輸出 CHANGELOG 對應版本 section body 後結束（供 release notes）",
    )
    args = parser.parse_args(argv)

    if args.extract_notes:
        try:
            print(extract_changelog_section(args.repo_root, args.extract_notes))
        except LookupError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        return 0

    offenders = check_consistency(args.repo_root, args.tag)
    if offenders:
        sys.stderr.write("release consistency FAIL:\n")
        for o in offenders:
            sys.stderr.write(f"  - {o}\n")
        return 1
    label = f" @ {args.tag}" if args.tag else ""
    v = read_version_file(args.repo_root)
    print(f"release consistency OK{label} (version {v})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())