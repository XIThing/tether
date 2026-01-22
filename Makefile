.PHONY: help agent-venv agent-install agent-dev agent-run ui-install ui-dev ui-build ui-build-prod fmt

PYTHON ?= python3
VENV_DIR ?= agent/.venv
VENV_BIN := $(VENV_DIR)/bin
PIP := $(VENV_BIN)/pip
PY := $(VENV_BIN)/python
BLACK := $(VENV_BIN)/black

help:
	@echo "Common targets:"
	@echo "  agent-venv      Create Python venv in agent/.venv"
	@echo "  agent-install   Install agent (editable)"
	@echo "  agent-dev       Install agent + dev tools (Black)"
	@echo "  agent-run       Run the agent server"
	@echo "  ui-install      Install UI deps"
	@echo "  ui-dev          Run UI dev server"
	@echo "  ui-build        Build UI (Vite)"
	@echo "  ui-build-prod   Build UI + copy into agent"
	@echo "  fmt             Format Python with Black"

agent-venv:
	$(PYTHON) -m venv $(VENV_DIR)

agent-install: agent-venv
	$(PIP) install -e agent

agent-dev: agent-venv
	$(PIP) install -e "agent[dev]"

agent-run: agent-install
	$(PY) -m tether.main

ui-install:
	cd ui && npm install

ui-dev: ui-install
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

ui-build-prod: ui-build
	./scripts/build_ui.sh

fmt: agent-dev
	$(BLACK) agent/tether
