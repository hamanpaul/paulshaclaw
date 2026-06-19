#!/usr/bin/env bash
# Thin wrapper: keep the scheduled dream path on the identity promoter so a
# local atomizer override cannot silently flip it into spawning a full Claude CLI.
set -euo pipefail
MEMORY_ROOT="${PSC_MEMORY_ROOT:-$HOME/.agents/memory}"
exec python3 -m paulshaclaw.memory.cli memory dream run --memory-root "$MEMORY_ROOT" --require-idle --promoter identity
