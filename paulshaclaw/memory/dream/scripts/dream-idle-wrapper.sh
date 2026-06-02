#!/usr/bin/env bash
# Thin wrapper: the idle gate lives in Python (--require-idle).
set -euo pipefail
MEMORY_ROOT="${PSC_MEMORY_ROOT:-$HOME/.agents/memory}"
exec python3 -m paulshaclaw.memory.cli memory dream run --memory-root "$MEMORY_ROOT" --require-idle
