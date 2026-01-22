# Tether (Phase 1 Scaffold)

Local-first control interface for supervising AI coding sessions.

Project name: **Tether**.

Note: The project is intentionally not tied to Codex specifically; the agent interface is meant to support other agentic systems in the future.

## Requirements

- Python 3.10+
- Node.js 18+

## Onboarding (local + mobile)

Follow these steps in order. Each step ends with a quick check so you can confirm it works.

Quick helper (optional):

```bash
./scripts/onboard.sh
```

One-command dev startup (runs agent + UI, optional Codex SDK sidecar):

```bash
./scripts/run_dev.sh
```

Enable the Codex SDK sidecar with:

```bash
USE_SIDECAR=1 ./scripts/run_dev.sh
```

Bind the agent to a specific host/port:

```bash
AGENT_HOST=0.0.0.0 AGENT_PORT=8787 ./scripts/run_dev.sh
```

One-command production build + serve:

```bash
./scripts/run_prod.sh
```

Bind the agent host/port in production:

```bash
AGENT_HOST=0.0.0.0 AGENT_PORT=8787 ./scripts/run_prod.sh
```

### 1) Start the agent backend

```bash
cd agent
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m tether.main
```

Quick check (on the same machine):

```bash
curl http://localhost:8787/api/health
```

Optional auth:

```bash
export AGENT_TOKEN=yourtoken
python -m tether.main
```

### 2) (Optional) Start the Codex SDK sidecar

The Codex SDK sidecar runs the Codex SDK locally and streams structured output to the agent. It is
optional and only used when `AGENT_ADAPTER=codex_sdk_sidecar`.

```bash
cd codex-sdk-sidecar
npm install
npm run dev
```

Then run the agent with:

```bash
export AGENT_ADAPTER=codex_sdk_sidecar
export CODEX_SDK_SIDECAR_URL=http://localhost:8788
python -m tether.main
```

The Codex SDK sidecar reads `CODEX_BIN` (path to the Codex CLI) from its environment.
Sidecar config (optional):

```bash
export CODEX_SDK_SIDECAR_PORT=8788
export CODEX_SDK_SIDECAR_HOST=127.0.0.1
export CODEX_SDK_SIDECAR_TOKEN=yourtoken
export CODEX_SDK_SIDECAR_LOG_LEVEL=info
export CODEX_SDK_SIDECAR_LOG_PRETTY=1
export CODEX_SDK_SIDECAR_LOG_EVENTS=0
export CODEX_SDK_SIDECAR_HEARTBEAT_SECONDS=5
export CODEX_SDK_SIDECAR_TURN_TIMEOUT_SECONDS=0
```

### 3) Start the UI (Vite dev server)

```bash
cd ui
npm install
npm run dev
```

Open the UI locally:

```
http://localhost:5173
```

### 4) Open the UI from another device on the same Wi‑Fi

1) Bind Vite to all interfaces:

```bash
npm run dev -- --host 0.0.0.0
```

2) Make sure the agent is also listening on all interfaces:

```bash
uvicorn tether.main:app --host 0.0.0.0 --port 8787
```

3) Open firewall ports on the host machine (see OS notes below).

Then open `http://<your_laptop_ip>:5173` on the phone.

Quick check (from the phone browser):

```
http://<your_laptop_ip>:8787/api/health
```

If it still doesn’t load, check for router “client isolation” (blocks device‑to‑device traffic)
or whether the phone is on a guest network.

#### Firewall notes by OS

Fedora (firewalld):

```bash
sudo firewall-cmd --add-port=5173/tcp --add-port=8787/tcp --permanent
sudo firewall-cmd --reload
```

Ubuntu/Debian (ufw):

```bash
sudo ufw allow 5173/tcp
sudo ufw allow 8787/tcp
sudo ufw status
```

Arch Linux:

- If using `ufw`, use the Ubuntu/Debian commands above.
- If using `firewalld`, use the Fedora commands above.
- If using `nftables` directly, allow inbound TCP 5173 and 8787 in your ruleset.

macOS:

- System Settings -> Network -> Firewall -> Options
- Allow incoming connections for Node (Vite) and Python (agent), or disable the firewall temporarily for testing.

#### Troubleshooting checklist

If the mobile UI shows a blank page or “could not connect”:

1) Confirm the agent is reachable:

```
http://<your_laptop_ip>:8787/api/health
```

2) Confirm the UI dev server is reachable:

```
http://<your_laptop_ip>:5173
```

3) Make sure the phone is on the same Wi‑Fi and not a guest network.

4) Check for router “client isolation” and disable it if enabled.

5) Check host firewall rules (ports 5173 and 8787).

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

Retention and log caps:

```bash
export AGENT_SESSION_RETENTION_DAYS=7
export AGENT_EVENT_LOG_MAX_BYTES=5000000
```

Timeouts and maintenance:

```bash
export AGENT_SESSION_IDLE_SECONDS=0
export AGENT_MAINTENANCE_SECONDS=60
export RUNNER_TURN_TIMEOUT_SECONDS=0
export CODEX_SDK_SIDECAR_TURN_TIMEOUT_SECONDS=0
```

## Codex SDK Sidecar (TypeScript, optional)

See onboarding step 2 for setup and environment variables.

## Frontend (Vue + Vite)

See onboarding step 3 for dev server usage. Vite proxies `/api` and `/events` to the agent.

## Production build

```bash
cd ui
npm run build
../scripts/build_ui.sh
cd ../agent
python -m tether.main
```

The UI is served from the agent at `/`.

## Smoke tests

```bash
python3 scripts/smoke_test.py
python3 scripts/runner_directory_smoke.py
```

Optional (start/stop session during directory test):

```bash
python3 scripts/runner_directory_smoke.py --start
```

If the agent requires auth, pass `--token` or set `AGENT_TOKEN`:

```bash
AGENT_TOKEN=yourtoken python3 scripts/smoke_test.py
```
