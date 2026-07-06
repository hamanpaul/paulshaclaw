#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$script_dir/.." && pwd)"
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
fi

_default_secret_env="$HOME/.config/paulshaclaw/paulshaclaw.telegram.secret.env"
_default_state_config="$HOME/.config/paulshaclaw/paulshaclaw.state.json"
if [[ -z "${PSC_TELEGRAM_BOT_TOKEN:-}" && -r "$_default_secret_env" ]]; then
  set -o allexport
  # shellcheck source=/dev/null
  source "$_default_secret_env"
  set +o allexport
fi
if [[ -z "${PSC_STAGE1_CONFIG:-}" && -r "$_default_state_config" ]]; then
  export PSC_STAGE1_CONFIG="$_default_state_config"
fi
unset _default_secret_env _default_state_config

telegram_token_present=0
telegram_config_present=0
telegram_config_readable=0
if [[ -n "${PSC_TELEGRAM_BOT_TOKEN:-}" ]]; then
  telegram_token_present=1
fi
if [[ -n "${PSC_STAGE1_CONFIG:-}" ]]; then
  telegram_config_present=1
  if [[ -r "${PSC_STAGE1_CONFIG}" ]]; then
    telegram_config_readable=1
  fi
fi

if [[ "$telegram_token_present" -eq 0 && "$telegram_config_present" -eq 0 ]]; then
  if [[ "${PSC_BOT_ALLOW_SKIP:-0}" == "1" ]]; then
    echo "telegram skipped: missing PSC_TELEGRAM_BOT_TOKEN or PSC_STAGE1_CONFIG"
    exit 0
  fi
  echo "telegram startup requires both PSC_TELEGRAM_BOT_TOKEN and readable PSC_STAGE1_CONFIG" >&2
  exit 1
elif [[ "$telegram_token_present" -eq 1 && "$telegram_config_present" -eq 1 && "$telegram_config_readable" -eq 1 ]]; then
  :
else
  echo "telegram startup requires both PSC_TELEGRAM_BOT_TOKEN and readable PSC_STAGE1_CONFIG" >&2
  exit 1
fi

TELEGRAM_READY_FILE="${PSC_TELEGRAM_READY_FILE:-$HOME/.agents/run/telegram.ready}"
mkdir -p "$(dirname "$TELEGRAM_READY_FILE")"
: > "$TELEGRAM_READY_FILE"
export PSC_TELEGRAM_READY_FILE="$TELEGRAM_READY_FILE"

exec env PYTHONPATH="$REPO" "$PY" -m paulshaclaw.bot.listener
