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
# Install dependencies (once)
make install

# Start agent
make start
open http://localhost:8787
```

Requirements: Python 3.10+, Node.js 20+

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
System Settings > Network > Firewall > Options > Allow incoming connections

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

### Native Mode (Recommended)
```bash
make install      # Install Python and Node dependencies (once)
make start        # Start agent with UI (localhost:8787)
make start-codex  # Start agent + Codex sidecar
make stop         # Stop sidecar container
make test         # Run tests
```

### Development
```bash
make dev-ui       # Run UI with hot reload (agent runs separately)
make dev          # Run sidecar + telegram in Docker for dev
make dev-stop     # Stop dev containers
```

### Docker Mode (Legacy)
For users who prefer Docker. Note: requires volume mounts for file access.
```bash
make docker-start        # Start agent in Docker
make docker-start-codex  # Start agent + sidecar in Docker
make docker-stop         # Stop all containers
make docker-logs         # View logs
make docker-build        # Rebuild images
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## Status

Early development. Feedback welcome.

---

[Website](https://gettether.dev) · Built by XIThing
