#!/usr/bin/env bash
set -euo pipefail

say() {
  printf "%s\n" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

load_token() {
  if [[ -f "${TOKEN_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${TOKEN_FILE}"
    set +a
  fi
}

generate_token() {
  require_cmd python3
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

ensure_token() {
  if [[ -n "${AGENT_TOKEN:-}" ]]; then
    return
  fi
  if [[ "${TOKEN_REQUIRED:-0}" != "1" && "${PROMPT_TOKEN:-0}" != "1" ]]; then
    return
  fi
  say "No AGENT_TOKEN found."
  read -r -p "Enter a token, or press Enter to generate one: " input_token
  if [[ -z "${input_token}" ]]; then
    input_token="$(generate_token)"
    say "Generated AGENT_TOKEN: ${input_token}"
  fi
  AGENT_TOKEN="${input_token}"
  {
    printf "AGENT_TOKEN=%s\n" "${AGENT_TOKEN}"
  } > "${TOKEN_FILE}"
  chmod 600 "${TOKEN_FILE}" 2>/dev/null || true
  export AGENT_TOKEN
  say "Saved token to ${TOKEN_FILE} (chmod 600)."
}
