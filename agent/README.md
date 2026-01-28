# Tether Agent

Control your AI coding agents from your phone when you're away from your desk.

You start a coding agent, walk away for lunch, and come back to find it stuck waiting for input for an hour. Tether fixes that. Get notified when your agent needs you, respond from anywhere.

## Features

- **Local-first** — Runs on your machine, your data stays yours
- **Multi-agent** — Supports Claude and Codex, more to come
- **Web UI** — Monitor sessions from your phone or desktop
- **No API keys required** — Uses Claude / Codex local OAuth by default

## Installation

```bash
pip install tether-agent
```

## Quick Start

```bash
# Start the agent server
tether-agent
```

Then open http://localhost:8787 in your browser.

## Configuration

Set environment variables to configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `TETHER_AGENT_HOST` | Host to bind to | `0.0.0.0` |
| `TETHER_AGENT_PORT` | Port to listen on | `8787` |
| `TETHER_AGENT_TOKEN` | Auth token (required unless dev mode) | — |
| `TETHER_AGENT_DEV_MODE` | Enable dev mode (no token required) | `0` |
| `TETHER_AGENT_ADAPTER` | AI adapter to use | `claude_local` |

### Adapters

| Adapter | Description |
|---------|-------------|
| `claude_local` | Claude via local OAuth (default, no API key) |
| `claude_api` | Claude via API key (set `ANTHROPIC_API_KEY`) |
| `claude_auto` | Auto-detect (prefer OAuth, fallback to API key) |
| `codex_sdk_sidecar` | Codex via sidecar |
| `codex_cli` | Legacy Codex CLI runner |

## Documentation

For full documentation, see [github.com/XIThing/tether](https://github.com/XIThing/tether).

## License

Apache 2.0. See [LICENSE](https://github.com/XIThing/tether/blob/main/LICENSE) for details.
