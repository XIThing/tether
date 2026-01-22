#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/scripts/lib_common.sh"

PORT_UI="${PORT_UI:-5173}"
PORT_AGENT="${PORT_AGENT:-8787}"
AGENT_HOST="${AGENT_HOST:-0.0.0.0}"
USE_SIDECAR="${USE_SIDECAR:-0}"
TOKEN_FILE="${TOKEN_FILE:-${ROOT_DIR}/agent/.env}"
TOKEN_REQUIRED="${TOKEN_REQUIRED:-0}"
if [[ "${TOKEN_REQUIRED}" != "1" && -z "${AGENT_DEV_MODE:-}" ]]; then
  export AGENT_DEV_MODE="1"
fi

start_sidecar() {
  if [[ "$USE_SIDECAR" != "1" ]]; then
    return 0
  fi
  require_cmd node
  require_cmd npm
  if [[ -z "${CODEX_SDK_SIDECAR_TOKEN:-}" && -n "${AGENT_TOKEN:-}" ]]; then
    export CODEX_SDK_SIDECAR_TOKEN="${AGENT_TOKEN}"
  fi
  say "[codex-sdk-sidecar] starting"
  (cd "${ROOT_DIR}/codex-sdk-sidecar" && npm run dev) &
  SIDECAR_PID=$!
}

start_agent() {
  require_cmd python3
  say "[agent] starting"
  (cd "${ROOT_DIR}/agent" && AGENT_HOST="${AGENT_HOST}" AGENT_PORT="${PORT_AGENT}" python3 -m tether.main) &
  AGENT_PID=$!
}

start_ui() {
  require_cmd node
  require_cmd npm
  say "[ui] starting (host 0.0.0.0)"
  (cd "${ROOT_DIR}/ui" && npm run dev -- --host 0.0.0.0 --port "${PORT_UI}") &
  UI_PID=$!
}

cleanup() {
  say ""
  say "Stopping processes..."
  if [[ -n "${UI_PID:-}" ]]; then kill "${UI_PID}" 2>/dev/null || true; fi
  if [[ -n "${AGENT_PID:-}" ]]; then kill "${AGENT_PID}" 2>/dev/null || true; fi
  if [[ -n "${SIDECAR_PID:-}" ]]; then kill "${SIDECAR_PID}" 2>/dev/null || true; fi
  wait || true
}

trap cleanup EXIT INT TERM

say "Tether - Dev launcher"
say "Ports: UI=${PORT_UI}, Agent=${PORT_AGENT}"

load_token
ensure_token
start_sidecar
start_agent
start_ui

say "All services started."
say "UI:    http://localhost:${PORT_UI}"
say "Health http://localhost:${PORT_AGENT}/api/health"
say "Press Ctrl+C to stop."

wait
