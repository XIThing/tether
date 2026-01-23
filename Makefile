.PHONY: start stop logs status build clean dev dev-stop

# Start the agent (default)
start:
	docker compose up -d agent

# Dev mode: run sidecar/telegram in Docker while agent+UI run locally
dev:
	docker compose -f docker-compose.dev.yml up

dev-stop:
	docker compose -f docker-compose.dev.yml down

# Start with Codex sidecar
start-codex:
	docker compose --profile codex up -d

# Start with Telegram bridge
start-telegram:
	docker compose --profile telegram up -d

# Stop all services
stop:
	docker compose --profile codex --profile telegram down

# View logs
logs:
	docker compose logs -f

# Show status
status:
	docker compose ps -a

# Rebuild images
build:
	docker compose build

# Remove containers and volumes
clean:
	docker compose --profile codex --profile telegram down -v
