#!/usr/bin/env bash
set -euo pipefail

PORT_UI="${PORT_UI:-5173}"
PORT_AGENT="${PORT_AGENT:-8787}"

say() {
  printf "%s\n" "$*"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

detect_os() {
  local uname_out
  uname_out="$(uname -s 2>/dev/null || true)"
  case "$uname_out" in
    Linux) echo "linux" ;;
    Darwin) echo "macos" ;;
    *) echo "unknown" ;;
  esac
}

detect_ip() {
  if have python3; then
    python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    print(s.getsockname()[0])
finally:
    try:
        s.close()
    except Exception:
        pass
PY
    return 0
  fi

  if have ip; then
    ip route get 8.8.8.8 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}'
    return 0
  fi

  echo ""
}

check_listen() {
  local port="$1"
  if have ss; then
    ss -ltn 2>/dev/null | awk '{print $4}' | rg -q "[:.]${port}$" && echo "yes" || echo "no"
    return 0
  fi
  if have lsof; then
    lsof -iTCP -sTCP:LISTEN -P 2>/dev/null | rg -q ":${port} " && echo "yes" || echo "no"
    return 0
  fi
  echo "unknown"
}

confirm_and_run() {
  local prompt="$1"
  shift
  if [[ -t 0 ]]; then
    read -r -p "${prompt} [y/N] " reply
    if [[ "$reply" == "y" || "$reply" == "Y" ]]; then
      "$@"
      return 0
    fi
  fi
  return 1
}

firewalld_has_port() {
  local port="$1"
  firewall-cmd --list-ports 2>/dev/null | rg -q "(^|\\s)${port}/tcp(\\s|$)"
}

ufw_has_port() {
  local port="$1"
  ufw status 2>/dev/null | rg -q "\\b${port}/tcp\\b"
}

firewall_hint() {
  local os="$1"
  if [[ "$os" == "linux" ]]; then
    if have firewall-cmd; then
      if firewall-cmd --state >/dev/null 2>&1; then
        say "Detected firewalld (active)."
        local need_ui=1
        local need_agent=1
        firewalld_has_port "${PORT_UI}" && need_ui=0
        firewalld_has_port "${PORT_AGENT}" && need_agent=0
        if [[ $need_ui -eq 0 && $need_agent -eq 0 ]]; then
          say "Ports ${PORT_UI} and ${PORT_AGENT} already allowed."
          return 0
        fi
        if ! confirm_and_run "Open missing ports with firewall-cmd?" \
          sudo firewall-cmd --add-port="${PORT_UI}/tcp" --add-port="${PORT_AGENT}/tcp" --permanent; then
          say "Suggested commands:"
          say "  sudo firewall-cmd --add-port=${PORT_UI}/tcp --add-port=${PORT_AGENT}/tcp --permanent"
        fi
        if ! confirm_and_run "Reload firewalld now?" sudo firewall-cmd --reload; then
          say "  sudo firewall-cmd --reload"
        fi
        return 0
      fi
    fi
    if have ufw; then
      if ufw status >/dev/null 2>&1; then
        if ufw status 2>/dev/null | rg -qi "Status: active"; then
          say "Detected ufw (active)."
          local need_ui=1
          local need_agent=1
          ufw_has_port "${PORT_UI}" && need_ui=0
          ufw_has_port "${PORT_AGENT}" && need_agent=0
          if [[ $need_ui -eq 0 && $need_agent -eq 0 ]]; then
            say "Ports ${PORT_UI} and ${PORT_AGENT} already allowed."
            return 0
          fi
          if ! confirm_and_run "Open missing ports with ufw?" sudo ufw allow "${PORT_UI}/tcp"; then
            say "Suggested commands:"
            say "  sudo ufw allow ${PORT_UI}/tcp"
          fi
          if ! confirm_and_run "Open agent port ${PORT_AGENT}?" sudo ufw allow "${PORT_AGENT}/tcp"; then
            say "  sudo ufw allow ${PORT_AGENT}/tcp"
          fi
          if ! confirm_and_run "Show ufw status?" sudo ufw status; then
            say "  sudo ufw status"
          fi
          return 0
        fi
      fi
    fi
    say "No active firewall tool detected. If you use nftables directly, allow inbound TCP ${PORT_UI} and ${PORT_AGENT}."
    return 0
  fi

  if [[ "$os" == "macos" ]]; then
    say "macOS firewall: System Settings -> Network -> Firewall -> Options"
    say "Allow incoming connections for Node (Vite) and Python (agent)."
    return 0
  fi
}

main() {
  local os ip ui_listen agent_listen
  os="$(detect_os)"
  ip="$(detect_ip)"
  ui_listen="$(check_listen "$PORT_UI")"
  agent_listen="$(check_listen "$PORT_AGENT")"

  say "Tether - Onboarding Helper"
  say "OS: ${os}"
  if [[ -n "$ip" ]]; then
    say "Detected IP: ${ip}"
    say "UI URL:    http://${ip}:${PORT_UI}"
    say "Health:    http://${ip}:${PORT_AGENT}/api/health"
  else
    say "Detected IP: (unknown)"
  fi

  say ""
  say "Port checks (listening on this machine):"
  say "- UI port ${PORT_UI}: ${ui_listen}"
  say "- Agent port ${PORT_AGENT}: ${agent_listen}"
  say ""
  say "Make sure Vite and the agent are bound to 0.0.0.0 for LAN access."
  say ""
  firewall_hint "$os"

  say ""
  say "If the phone still can’t connect:" 
  say "- Ensure the phone is on the same Wi-Fi (not guest)."
  say "- Disable router client isolation."
}

main "$@"
