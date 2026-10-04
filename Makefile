# Shortcuts for common tasks. Every target wraps a plain docker compose / manage.py command,
# so the system also runs without make: `docker compose up --build`.
#
# Two ways to run:
#   Local dev  - Django from a venv on your machine (auto-reload), only Postgres in Docker.
#                make server | web | migrate | migrations | shell | test-local
#   Full stack - everything in Docker, exactly what a reviewer runs.
#                make up | down | logs | test

COMPOSE := docker compose
VENV    := backend/.venv
PYTHON  := $(VENV)/bin/python
MANAGE  := cd backend && .venv/bin/python manage.py
PORT    ?= 8000

.DEFAULT_GOAL := help
.PHONY: help install db server web seed import migrate migrations check-migrations shell dbshell test-local \
        up down reset logs test clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2}'

# --- Local development ---------------------------------------------------------

# Re-installs automatically whenever a requirements file changes.
$(VENV)/.installed: backend/requirements.txt backend/requirements-dev.txt
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -q --upgrade pip
	$(PYTHON) -m pip install -q -r backend/requirements-dev.txt
	@touch $@
	@echo "Installed backend dependencies into $(VENV)"

.env:
	cp .env.example .env
	@echo "Created .env from .env.example"

install: $(VENV)/.installed .env ## Create the local venv, install dependencies, create .env

db: ## Start only Postgres (published on localhost:55432)
	$(COMPOSE) up -d --wait db

server: install db ## Run the backend locally with auto-reload: migrate, then runserver (PORT=8000)
	$(MANAGE) migrate
	$(MANAGE) runserver $(PORT)

frontend/node_modules/.installed: frontend/package.json frontend/package-lock.json
	@cd frontend && npm ci --silent
	@touch $@

web: frontend/node_modules/.installed ## Run the frontend dev server on :5173 (proxies /api to :8000)
	@cd frontend && npm run dev

seed: install db ## Create/update the seed accounts from seed/users.json
	@$(MANAGE) seed_users ../seed/users.json

import: install db ## Import an episodes CSV locally: make import FILE=seed/episodes.csv
	@$(MANAGE) import_episodes $(abspath $(FILE))

migrate: install db ## Apply migrations to the database
	$(MANAGE) migrate

migrations: install db ## Create migrations after a model change (optionally APP=accounts)
	$(MANAGE) makemigrations $(APP)

check-migrations: install db ## Fail if a model change has no migration
	$(MANAGE) makemigrations --check --dry-run

shell: install db ## Django shell
	$(MANAGE) shell

dbshell: db ## psql into the database
	$(COMPOSE) exec db psql -U requestdesk -d requestdesk

test-local: install db ## Run the tests from the venv (fast; ARGS="-k health" to filter)
	cd backend && .venv/bin/pytest $(ARGS)

# --- Full stack in Docker ------------------------------------------------------

up: ## Build and start everything in Docker (migrations run on start-up)
	$(COMPOSE) up --build -d --wait
	@echo "API running: http://localhost:8000/health"

down: ## Stop the Docker stack (keeps the data)
	$(COMPOSE) down

reset: ## Stop the Docker stack and DELETE the database volume
	$(COMPOSE) down -v

logs: ## Follow the API logs (JSON, one line per request)
	$(COMPOSE) logs -f api

test: db ## Run the tests in Docker, no local setup needed (ARGS="-k health" to filter)
	$(COMPOSE) run --rm --build api pytest $(ARGS)

clean: ## Remove the local venv and caches
	rm -rf $(VENV) backend/.pytest_cache
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
