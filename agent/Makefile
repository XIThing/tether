.PHONY: help install install-all dev test format lint clean migrate mcp docker-build docker-up docker-down

help:
	@echo "Tether Agent - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install      - Install package with core dependencies"
	@echo "  make install-all  - Install with all optional dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Run development server with auto-reload"
	@echo "  make test         - Run test suite"
	@echo "  make format       - Format code with black"
	@echo "  make lint         - Run linters"
	@echo ""
	@echo "Database:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make migration    - Create new migration (MESSAGE required)"
	@echo ""
	@echo "Servers:"
	@echo "  make mcp          - Run MCP server"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up    - Start services with docker-compose"
	@echo "  make docker-down  - Stop docker-compose services"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        - Remove build artifacts and caches"

install:
	pip install -e .

install-all:
	pip install -e ".[dev,telegram,slack,discord,mcp]"

dev:
	uvicorn tether.main:app --reload --host 0.0.0.0 --port 8787

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=tether --cov-report=html --cov-report=term

format:
	black tether/ tests/

lint:
	black --check tether/ tests/

migrate:
	alembic upgrade head

migration:
	@if [ -z "$(MESSAGE)" ]; then \
		echo "Error: MESSAGE required. Usage: make migration MESSAGE='description'"; \
		exit 1; \
	fi
	alembic revision --autogenerate -m "$(MESSAGE)"

mcp:
	python -m tether.mcp.server

docker-build:
	docker build -t tether-agent:latest -f Dockerfile ..

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
