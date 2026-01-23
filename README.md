# Tether

Local-first control interface for supervising AI coding sessions from your phone.

## Quick Start

```bash
# Start the agent
make start

# Open in browser
open http://localhost:8787
```

The agent uses Claude via local OAuth by default (no API key needed).

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
| `codex_sdk_sidecar` | Codex via sidecar (use `make start-codex`) |

### Authentication

By default, no auth is required. To require a token:

```bash
TETHER_AGENT_TOKEN=your-secret-token make start
```

## Commands

```bash
make start          # Start agent
make start-codex    # Start agent + Codex sidecar
make start-telegram # Start agent + Telegram bridge
make stop           # Stop all services
make logs           # View logs
make status         # Show container status
make build          # Rebuild images
make clean          # Remove containers and volumes
```

## Development

### Agent (Python)

```bash
cd agent
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### UI (Vue)

```bash
cd ui
npm install
npm run dev
```

### Run Tests

```bash
cd agent && pytest
```
