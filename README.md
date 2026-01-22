# Codex on Mobile (Phase 1 Scaffold)

Local-first control interface for supervising AI coding sessions.

Note: The project is intentionally not tied to Codex specifically; the agent interface is meant to support other agentic systems in the future.

## Requirements

- Python 3.10+
- Node.js 18+

## Backend (FastAPI)

```bash
cd agent
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m tether.main
```

Agent listens on `http://localhost:8787`.

Optional auth:

```bash
export AGENT_TOKEN=yourtoken
python -m tether.main
```

### Persistence

- Session metadata is stored in SQLite at `agent/data/sessions.db`.
- Per-session event logs are appended as JSONL at `agent/data/sessions/<id>/events.jsonl`.

Override the data directory with:

```bash
export AGENT_DATA_DIR=/path/to/data
```

## Codex Sidecar (TypeScript, optional)

The sidecar runs the Codex SDK locally and streams structured output to the agent. It is
optional and only used when `AGENT_ADAPTER=sidecar`.

```bash
cd sidecar
npm install
npm run dev
```

Then run the agent with:

```bash
export AGENT_ADAPTER=sidecar
export SIDECAR_URL=http://localhost:8788
python -m tether.main
```

The sidecar reads `CODEX_BIN` (path to the Codex CLI) from its environment.

## Frontend (Vue + Vite)

```bash
cd ui
npm install
npm run dev
```

Vite proxies `/api` and `/events` to the agent.

## Production build

```bash
cd ui
npm run build
../scripts/build_ui.sh
cd ../agent
python -m tether.main
```

The UI is served from the agent at `/`.
