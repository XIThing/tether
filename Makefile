.PHONY: start start-codex stop build-ui install verify \
        docker-start docker-start-codex docker-stop docker-logs docker-status docker-build docker-clean \
        dev dev-ui dev-stop test

# =============================================================================
# Native mode (recommended)
# =============================================================================

# Install dependencies (run once)
install:
	cd agent && pip install -e ".[dev]"
	cd ui && npm ci

# Build UI for production
build-ui:
	cd ui && npm run build
	rm -rf agent/tether/static_ui
	cp -r ui/dist agent/tether/static_ui

# Start agent natively (Claude works out of the box)
start: build-ui
	cd agent && python -m tether.main

# Start agent + Codex sidecar (sidecar runs in Docker)
start-codex: build-ui
	docker compose -f docker-compose.sidecar.yml up -d
	cd agent && python -m tether.main

# Stop sidecar container
stop:
	docker compose -f docker-compose.sidecar.yml down 2>/dev/null || true

# =============================================================================
# Development mode
# =============================================================================

# Run UI dev server (hot reload) - run agent separately
dev-ui:
	cd ui && npm run dev

# Run sidecar + telegram in Docker for development
dev:
	docker compose -f docker-compose.dev.yml up

dev-stop:
	docker compose -f docker-compose.dev.yml down

# Run tests
test:
	cd agent && pytest

# Verify setup (agent must be running)
verify:
	./scripts/verify.sh

# =============================================================================
# Docker mode (legacy - for users who prefer Docker with volume mounts)
# =============================================================================

docker-start:
	docker compose up -d agent

docker-start-codex:
	docker compose --profile codex up -d

docker-start-telegram:
	docker compose --profile telegram up -d

docker-stop:
	docker compose --profile codex --profile telegram down

docker-logs:
	docker compose logs -f

docker-status:
	docker compose ps -a

docker-build:
	docker compose build

docker-clean:
	docker compose --profile codex --profile telegram down -v
