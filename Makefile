# Every command Claude Code may run lives here. Never "run the thing in the
# other terminal" — if it is not a target, it does not exist.

.DEFAULT_GOAL := help
.PHONY: help dev down logs test test-api test-ops lint lint-api lint-ops fmt migrate \
	migration seed contracts eval deploy

# Two generated prerequisites, declared as *files* rather than as phony targets
# so make rebuilds them only when they are missing. `generated.ts` is gitignored,
# so on a fresh clone — and on every CI run — it does not exist and is built
# once; afterwards `make lint` does not pay for a regeneration it does not need.
#
# The trade-off is deliberate: an API change does not invalidate these
# automatically, and `make contracts` stays the explicit step you run after
# touching a schema. CI always starts from an empty checkout, so it always
# regenerates and always sees drift.
GENERATED_TS := packages/contracts/src/generated.ts
OPS_MODULES := apps/ops/node_modules

$(GENERATED_TS):
	$(MAKE) contracts

$(OPS_MODULES):
	npm --prefix apps/ops install --no-audit --no-fund --silent

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev: ## Full stack up via Docker Compose
	docker compose up --build

down: ## Stop the stack, keep volumes
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

test: test-api test-ops ## pytest (API) + vitest (ops console)

test-api:
	uv run pytest

test-ops: $(OPS_MODULES)
	npm --prefix apps/ops run test

lint: lint-api lint-ops ## ruff + ruff format --check + mypy + the console's typecheck

lint-api:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

# The console is typechecked, not merely built. `tsc --noEmit` is what makes
# `packages/contracts` load-bearing: without this step the generated types are
# a suggestion, and a component reading a field the API stopped sending gets
# found by an operator instead of by CI.
lint-ops: $(OPS_MODULES) $(GENERATED_TS)
	npm --prefix apps/ops run typecheck

fmt: ## ruff format + ruff check --fix
	uv run ruff format .
	uv run ruff check --fix .

migrate: ## Apply Alembic migrations
	uv run alembic -c apps/api/alembic.ini upgrade head

migration: ## Autogenerate a new revision — make migration m="add hotels"
	@test -n "$(m)" || (echo 'usage: make migration m="describe the change"'; exit 1)
	uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "$(m)"

# Development data. Idempotent, so running it twice is not a mistake — the ops
# console needs a real city_id to ask for anything, and a fresh checkout has no
# rows to supply one.
seed: ## Insert a city and sample hotels into the development database
	uv run python apps/api/scripts/seed.py

# Three steps, each of which must be able to fail loudly: dump the schema from
# the Python app, generate types from it, then typecheck them. The last step is
# what makes this a contract rather than a code dump — `src/index.ts` names the
# schemas it expects, so a rename on the Python side fails here instead of
# silently degrading a console component to `any`.
contracts: ## Regenerate packages/contracts/ TS types from OpenAPI
	uv run python apps/api/scripts/export_openapi.py packages/contracts/openapi.json
	npm --prefix packages/contracts install --no-audit --no-fund --silent
	npm --prefix packages/contracts run generate
	npm --prefix packages/contracts run typecheck

eval: ## Eval suite (M2 onward; a no-op stub today)
	@echo "eval suite is a no-op stub until M2"

deploy: ## The single deploy command, identical everywhere
	@echo "not wired yet — arrives with Stage 1 deploy (M1 slice 6)"
	@exit 1
