#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILURES=0

pass() {
  echo "PASS: $1"
}

fail() {
  echo "FAIL: $1" >&2
  FAILURES=$((FAILURES + 1))
}

assert_contains() {
  local file="$1"
  local needle="$2"
  local label="$3"

  if grep -Fq "$needle" "$file"; then
    pass "$label"
  else
    fail "$label (missing: $needle)"
  fi
}

assert_not_contains() {
  local file="$1"
  local needle="$2"
  local label="$3"

  if grep -Fq "$needle" "$file"; then
    fail "$label (unexpected: $needle)"
  else
    pass "$label"
  fi
}

strip_frontmatter() {
  local file="$1"
  awk '
    /^---$/ { separators += 1; next }
    separators >= 2 { print }
  ' "$file"
}

assert_docs_in_sync() {
  local prompt_file="$1"
  local command_file="$2"
  local label="$3"

  if diff -u <(strip_frontmatter "$prompt_file") <(strip_frontmatter "$command_file") >/dev/null; then
    pass "$label"
  else
    fail "$label"
  fi
}

assert_branch_map_matches_remote() {
  local map_file="$ROOT_DIR/config/worktrees/stage-worktrees.tsv"
  local branch
  local missing=0

  while IFS=$'\t' read -r workstream branch _dir _stage; do
    [[ "$workstream" == "workstream" ]] && continue
    [[ -z "$workstream" ]] && continue
    if git -C "$ROOT_DIR" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
      pass "remote branch exists: $branch"
    else
      fail "remote branch missing: $branch"
      missing=1
    fi
  done < "$map_file"

  return "$missing"
}

assert_remote_branch_tracking() {
  local tmpdir remote seed repo map_file worktree_root worktree upstream
  tmpdir="$(mktemp -d)"
  remote="$tmpdir/remote.git"
  seed="$tmpdir/seed"
  repo="$tmpdir/repo"
  map_file="$repo/config/worktrees/stage-worktrees.tsv"
  worktree_root="$tmpdir/worktrees"
  worktree="$worktree_root/demo"
  trap "git -C '$repo' worktree remove --force '$worktree' >/dev/null 2>&1 || true; rm -rf '$tmpdir'" RETURN

  git init --bare --initial-branch=main "$remote" >/dev/null
  git init --initial-branch=main "$seed" >/dev/null
  git -C "$seed" remote add origin "$remote"
  git -C "$seed" config user.name "stage0-test"
  git -C "$seed" config user.email "stage0-test@example.invalid"

  printf 'base\n' > "$seed/README.md"
  git -C "$seed" add README.md
  git -C "$seed" commit -m "base" >/dev/null
  git -C "$seed" branch -M main
  git -C "$seed" push -u origin main >/dev/null 2>&1

  git -C "$seed" checkout -b wt/demo >/dev/null 2>&1
  printf 'tracked remote branch\n' > "$seed/demo.txt"
  git -C "$seed" add demo.txt
  git -C "$seed" commit -m "remote branch" >/dev/null
  git -C "$seed" push -u origin wt/demo >/dev/null 2>&1

  git clone --quiet --branch main "$remote" "$repo"
  git -C "$repo" config user.name "stage0-test"
  git -C "$repo" config user.email "stage0-test@example.invalid"
  git -C "$repo" update-ref -d refs/remotes/origin/wt/demo

  mkdir -p "$repo/scripts"
  cp "$ROOT_DIR/scripts/using-git-worktrees.sh" "$repo/scripts/using-git-worktrees.sh"
  chmod +x "$repo/scripts/using-git-worktrees.sh"

  mkdir -p "$(dirname "$map_file")"
  printf 'workstream\tbranch\tworktree_dir\tstage\nstage0-demo\twt/demo\tdemo\t0\n' > "$map_file"

  "$repo/scripts/using-git-worktrees.sh" "$map_file" "$worktree_root" main >/dev/null 2>&1

  upstream="$(git -C "$worktree" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  if [[ "$upstream" == "origin/wt/demo" ]]; then
    pass "using-git-worktrees tracks remote branch when local remote ref is absent"
  else
    fail "using-git-worktrees should track origin/wt/demo when local remote ref is absent (got: ${upstream:-<none>})"
  fi

  if [[ -f "$worktree/demo.txt" ]]; then
    pass "remote branch content is present after refreshing missing remote ref"
  else
    fail "remote branch content should exist after refreshing missing remote ref"
  fi

}

assert_stale_remote_branch_refresh() {
  local tmpdir remote seed repo map_file worktree_root worktree upstream
  tmpdir="$(mktemp -d)"
  remote="$tmpdir/remote.git"
  seed="$tmpdir/seed"
  repo="$tmpdir/repo"
  map_file="$repo/config/worktrees/stage-worktrees.tsv"
  worktree_root="$tmpdir/worktrees"
  worktree="$worktree_root/stale-demo"
  trap "git -C '$repo' worktree remove --force '$worktree' >/dev/null 2>&1 || true; rm -rf '$tmpdir'" RETURN

  git init --bare --initial-branch=main "$remote" >/dev/null
  git init --initial-branch=main "$seed" >/dev/null
  git -C "$seed" remote add origin "$remote"
  git -C "$seed" config user.name "stage0-test"
  git -C "$seed" config user.email "stage0-test@example.invalid"

  printf 'base\n' > "$seed/README.md"
  git -C "$seed" add README.md
  git -C "$seed" commit -m "base" >/dev/null
  git -C "$seed" push -u origin main >/dev/null 2>&1

  git -C "$seed" checkout -b wt/stale-demo >/dev/null 2>&1
  printf 'remote version 1\n' > "$seed/stale.txt"
  git -C "$seed" add stale.txt
  git -C "$seed" commit -m "stale v1" >/dev/null
  git -C "$seed" push -u origin wt/stale-demo >/dev/null 2>&1

  git clone --quiet --branch main "$remote" "$repo"
  git -C "$repo" config user.name "stage0-test"
  git -C "$repo" config user.email "stage0-test@example.invalid"

  printf 'remote version 2\n' > "$seed/stale.txt"
  git -C "$seed" add stale.txt
  git -C "$seed" commit -m "stale v2" >/dev/null
  git -C "$seed" push origin wt/stale-demo >/dev/null 2>&1

  mkdir -p "$repo/scripts"
  cp "$ROOT_DIR/scripts/using-git-worktrees.sh" "$repo/scripts/using-git-worktrees.sh"
  chmod +x "$repo/scripts/using-git-worktrees.sh"

  mkdir -p "$(dirname "$map_file")"
  printf 'workstream\tbranch\tworktree_dir\tstage\nstage0-stale\twt/stale-demo\tstale-demo\t0\n' > "$map_file"

  "$repo/scripts/using-git-worktrees.sh" "$map_file" "$worktree_root" main >/dev/null 2>&1

  upstream="$(git -C "$worktree" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  if [[ "$upstream" == "origin/wt/stale-demo" ]] && grep -Fq 'remote version 2' "$worktree/stale.txt"; then
    pass "using-git-worktrees refreshes stale remote-tracking refs before checkout"
  else
    fail "using-git-worktrees 應在 remote ref 已 stale 時抓到最新 origin/wt/stale-demo"
  fi
}

assert_local_branch_path() {
  local tmpdir remote seed repo map_file worktree_root worktree
  tmpdir="$(mktemp -d)"
  remote="$tmpdir/remote.git"
  seed="$tmpdir/seed"
  repo="$tmpdir/repo"
  map_file="$repo/config/worktrees/stage-worktrees.tsv"
  worktree_root="$tmpdir/worktrees"
  worktree="$worktree_root/local-demo"
  trap "git -C '$repo' worktree remove --force '$worktree' >/dev/null 2>&1 || true; rm -rf '$tmpdir'" RETURN

  git init --bare --initial-branch=main "$remote" >/dev/null
  git init --initial-branch=main "$seed" >/dev/null
  git -C "$seed" remote add origin "$remote"
  git -C "$seed" config user.name "stage0-test"
  git -C "$seed" config user.email "stage0-test@example.invalid"

  printf 'base\n' > "$seed/README.md"
  git -C "$seed" add README.md
  git -C "$seed" commit -m "base" >/dev/null
  git -C "$seed" push -u origin main >/dev/null 2>&1

  git clone --quiet --branch main "$remote" "$repo"
  git -C "$repo" config user.name "stage0-test"
  git -C "$repo" config user.email "stage0-test@example.invalid"
  git -C "$repo" checkout -b wt/local-demo >/dev/null 2>&1
  printf 'local branch only\n' > "$repo/local-only.txt"
  git -C "$repo" add local-only.txt
  git -C "$repo" commit -m "local branch" >/dev/null

  mkdir -p "$repo/scripts"
  cp "$ROOT_DIR/scripts/using-git-worktrees.sh" "$repo/scripts/using-git-worktrees.sh"
  chmod +x "$repo/scripts/using-git-worktrees.sh"

  mkdir -p "$(dirname "$map_file")"
  printf 'workstream\tbranch\tworktree_dir\tstage\nstage0-local\twt/local-demo\tlocal-demo\t0\n' > "$map_file"

  git -C "$repo" checkout main >/dev/null 2>&1
  "$repo/scripts/using-git-worktrees.sh" "$map_file" "$worktree_root" main >/dev/null 2>&1

  if [[ -f "$worktree/local-only.txt" ]]; then
    pass "using-git-worktrees 保留既有 local branch 流程"
  else
    fail "using-git-worktrees 應直接掛載既有 local branch"
  fi
}

assert_new_branch_path() {
  local tmpdir remote seed repo map_file worktree_root worktree upstream
  tmpdir="$(mktemp -d)"
  remote="$tmpdir/remote.git"
  seed="$tmpdir/seed"
  repo="$tmpdir/repo"
  map_file="$repo/config/worktrees/stage-worktrees.tsv"
  worktree_root="$tmpdir/worktrees"
  worktree="$worktree_root/new-demo"
  trap "git -C '$repo' worktree remove --force '$worktree' >/dev/null 2>&1 || true; rm -rf '$tmpdir'" RETURN

  git init --bare --initial-branch=main "$remote" >/dev/null
  git init --initial-branch=main "$seed" >/dev/null
  git -C "$seed" remote add origin "$remote"
  git -C "$seed" config user.name "stage0-test"
  git -C "$seed" config user.email "stage0-test@example.invalid"

  printf 'base\n' > "$seed/README.md"
  git -C "$seed" add README.md
  git -C "$seed" commit -m "base" >/dev/null
  git -C "$seed" push -u origin main >/dev/null 2>&1

  git clone --quiet --branch main "$remote" "$repo"
  git -C "$repo" config user.name "stage0-test"
  git -C "$repo" config user.email "stage0-test@example.invalid"

  mkdir -p "$repo/scripts"
  cp "$ROOT_DIR/scripts/using-git-worktrees.sh" "$repo/scripts/using-git-worktrees.sh"
  chmod +x "$repo/scripts/using-git-worktrees.sh"

  mkdir -p "$(dirname "$map_file")"
  printf 'workstream\tbranch\tworktree_dir\tstage\nstage0-new\twt/new-demo\tnew-demo\t0\n' > "$map_file"

  "$repo/scripts/using-git-worktrees.sh" "$map_file" "$worktree_root" main >/dev/null 2>&1

  upstream="$(git -C "$worktree" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  if [[ -z "$upstream" && -f "$worktree/README.md" ]]; then
    pass "using-git-worktrees 保留從 BASE_REF 建新 branch 流程"
  else
    fail "using-git-worktrees 應在無 local/remote branch 時從 BASE_REF 建新 branch"
  fi
}

main() {
  assert_not_contains \
    "$ROOT_DIR/openspec/specs/stage0/tool-matrix.md" \
    "TBD" \
    "tool-matrix refine PR 欄位不得保留 TBD"

  assert_contains \
    "$ROOT_DIR/.github/prompts/opsx-new.prompt.md" \
    "寫入邊界" \
    "opsx:new prompt 必須要求寫入邊界"
  assert_contains \
    "$ROOT_DIR/.github/prompts/opsx-new.prompt.md" \
    "證據路徑" \
    "opsx:new prompt 必須要求證據路徑"
  assert_contains \
    "$ROOT_DIR/.claude/commands/opsx/new.md" \
    "寫入邊界" \
    "claude opsx:new 文件必須要求寫入邊界"
  assert_contains \
    "$ROOT_DIR/.claude/commands/opsx/new.md" \
    "證據路徑" \
    "claude opsx:new 文件必須要求證據路徑"

  assert_contains \
    "$ROOT_DIR/.github/prompts/opsx-ff.prompt.md" \
    "證據路徑" \
    "opsx:ff prompt 必須宣告證據路徑"
  assert_contains \
    "$ROOT_DIR/.claude/commands/opsx/ff.md" \
    "證據路徑" \
    "claude opsx:ff 文件必須宣告證據路徑"
  assert_docs_in_sync \
    "$ROOT_DIR/.github/prompts/opsx-new.prompt.md" \
    "$ROOT_DIR/.claude/commands/opsx/new.md" \
    "opsx:new prompt 與 claude command 內容必須同步"
  assert_docs_in_sync \
    "$ROOT_DIR/.github/prompts/opsx-ff.prompt.md" \
    "$ROOT_DIR/.claude/commands/opsx/ff.md" \
    "opsx:ff prompt 與 claude command 內容必須同步"

  assert_contains \
    "$ROOT_DIR/docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md" \
    "/opsx:new" \
    "Stage 0 規範需納入 /opsx:new"
  assert_contains \
    "$ROOT_DIR/docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md" \
    "/opsx:ff" \
    "Stage 0 規範需納入 /opsx:ff"
  assert_contains \
    "$ROOT_DIR/docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md" \
    "證據路徑" \
    "Stage 0 規範需要求證據路徑"
  assert_contains \
    "$ROOT_DIR/docs/superpowers/workstreams/stage0-tooling-foundation/plan.md" \
    ".github/prompts/opsx-new.prompt.md" \
    "workstream plan Relevant files 必須納入 opsx:new prompt"
  assert_contains \
    "$ROOT_DIR/docs/superpowers/workstreams/stage0-tooling-foundation/plan.md" \
    ".github/prompts/opsx-ff.prompt.md" \
    "workstream plan Relevant files 必須納入 opsx:ff prompt"
  assert_contains \
    "$ROOT_DIR/docs/superpowers/workstreams/stage0-tooling-foundation/plan.md" \
    ".claude/commands/opsx/new.md" \
    "workstream plan Relevant files 必須納入 claude opsx:new 文件"
  assert_contains \
    "$ROOT_DIR/docs/superpowers/workstreams/stage0-tooling-foundation/plan.md" \
    ".claude/commands/opsx/ff.md" \
    "workstream plan Relevant files 必須納入 claude opsx:ff 文件"

  assert_branch_map_matches_remote
  assert_remote_branch_tracking
  assert_stale_remote_branch_refresh
  assert_local_branch_path
  assert_new_branch_path

  if ((FAILURES > 0)); then
    echo
    echo "Stage 0 tooling foundation checks failed: $FAILURES"
    exit 1
  fi

  echo
  echo "Stage 0 tooling foundation checks passed"
}

main "$@"
