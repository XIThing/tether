#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/scripts/lib_common.sh"
PORT_AGENT="${PORT_AGENT:-8787}"
AGENT_HOST="${AGENT_HOST:-0.0.0.0}"
TOKEN_FILE="${TOKEN_FILE:-${ROOT_DIR}/agent/.env}"
TOKEN_REQUIRED="${TOKEN_REQUIRED:-1}"

build_ui() {
  require_cmd npm
  say "[ui] build"
  (cd "${ROOT_DIR}/ui" && npm install && npm run build)
  say "[ui] copy build"
  (cd "${ROOT_DIR}" && ./scripts/build_ui.sh)
}

start_agent() {
  require_cmd python3
  say "[agent] starting"
  (cd "${ROOT_DIR}/agent" && AGENT_HOST="${AGENT_HOST}" AGENT_PORT="${PORT_AGENT}" python3 -m tether.main) &
  AGENT_PID=$!
}

cleanup() {
  say ""
  say "Stopping agent..."
  if [[ -n "${AGENT_PID:-}" ]]; then kill "${AGENT_PID}" 2>/dev/null || true; fi
  wait || true
}

trap cleanup EXIT INT TERM

say "Tether - Prod launcher"
say "Agent port: ${PORT_AGENT}"

load_token
ensure_token
build_ui
start_agent

say "UI served from agent:"
say "http://localhost:${PORT_AGENT}"
say "Press Ctrl+C to stop."

wait
