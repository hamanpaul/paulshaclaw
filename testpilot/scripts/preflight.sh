#!/usr/bin/env bash
set -euo pipefail
plugin_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_venv="$plugin_root/.venv"
if [[ ! -x "$plugin_venv/bin/python" ]]; then
  python3 -m venv "$plugin_venv"
fi
"$plugin_venv/bin/python" -m pip install --quiet \
  'https://github.com/hamanpaul/testpilot-core/releases/download/v0.3.7/testpilot_core-0.3.7-py3-none-any.whl#sha256=d3bc7bd5efc7f31938116eb32daafc552a61d503cdb9af388c7694a997782a02' pytest build
"$plugin_venv/bin/python" -m pip install --quiet --force-reinstall --no-deps "$plugin_root"
# Verify the installed wheel from outside the checkout; tests explicitly import source.
cd "${TMPDIR:-/tmp}"
"$plugin_venv/bin/testpilot" list-plugins
"$plugin_venv/bin/testpilot" list-cases paulshaclaw_deploy
"$plugin_venv/bin/python" "$plugin_root/scripts/verify_install.py"
"$plugin_venv/bin/python" -m pytest "$plugin_root/tests" -q
