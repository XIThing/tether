# Tether

Control your AI agents from your phone when you're away from your desk.

You start a coding agent, walk away for lunch, and come back to find it stuck waiting for input for an hour. Tether fixes that—get notified when your agent needs you, respond from anywhere.

## Features

- **Local-first** — Runs on your machine, your data stays yours
- **Multi-agent** — Supports Claude and Codex
- **Web UI** — Monitor sessions from your phone or desktop
- **No API key required** — Uses Claude local OAuth by default

## Quick Start
```bash
make start
open http://localhost:8787
```

## Access from Phone

1. Find your computer's IP address
2. Open firewall port 8787 (see below)
3. Open `http://<your-ip>:8787` on your phone

### Firewall Commands

**Linux (firewalld):**
```bash
sudo firewall-cmd --add-port=8787/tcp --permanent && sudo firewall-cmd --reload
```

**Linux (ufw):**
```bash
sudo ufw allow 8787/tcp
```

**macOS:**
System Settings → Network → Firewall → Options → Allow incoming connections for Docker

## Configuration

Copy `.env.example` to `.env` to customize settings.

### Adapters

Set `TETHER_AGENT_ADAPTER` in `.env`:

| Adapter | Description |
|---------|-------------|
| `claude_local` | Claude via local OAuth (default, no API key) |
| `claude` | Claude via API key (set `ANTHROPIC_API_KEY`) |
| `claude_auto` | Auto-detect (prefer OAuth, fallback to API key) |
| `codex_sdk_sidecar` | Codex via sidecar (use `make start-codex`) |
| `codex_cli` | Legacy Codex CLI runner |

### Authentication

By default, no auth is required. To require a token:
```bash
TETHER_AGENT_TOKEN=your-secret-token make start
```

## Commands
```bash
make start        # Start agent with UI (localhost:8787)
make start-codex  # Start agent with UI + Codex sidecar
make stop         # Stop all services
make logs         # View logs
make status       # Show container status
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## Status

Early development. Feedback welcome.

---

[Website](https://gettether.dev) · Built by XIThing