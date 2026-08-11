# Every command Claude Code may run lives here. Never "run the thing in the
# other terminal" — if it is not a target, it does not exist.

.DEFAULT_GOAL := help
.PHONY: help dev down logs test lint fmt migrate migration contracts eval deploy

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev: ## Full stack up via Docker Compose
	docker compose up --build

down: ## Stop the stack, keep volumes
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

test: ## pytest, API
	uv run pytest

lint: ## ruff + ruff format --check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

fmt: ## ruff format + ruff check --fix
	uv run ruff format .
	uv run ruff check --fix .

migrate: ## Apply Alembic migrations
	uv run alembic -c apps/api/alembic.ini upgrade head

migration: ## Autogenerate a new revision — make migration m="add hotels"
	@test -n "$(m)" || (echo 'usage: make migration m="describe the change"'; exit 1)
	uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "$(m)"

contracts: ## Regenerate packages/contracts/ TS types from OpenAPI
	@echo "not wired yet — arrives with the first real API surface (M1 slice 3)"
	@exit 1

eval: ## Eval suite (M2 onward; a no-op stub today)
	@echo "eval suite is a no-op stub until M2"

deploy: ## The single deploy command, identical everywhere
	@echo "not wired yet — arrives with Stage 1 deploy (M1 slice 6)"
	@exit 1
