# Contributing

## Development Commands

```bash
make dev       # Run sidecar in Docker, agent+UI locally
make dev-stop  # Stop dev containers
make build     # Rebuild Docker images
make clean     # Remove containers and volumes
```

## Development Setup

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
