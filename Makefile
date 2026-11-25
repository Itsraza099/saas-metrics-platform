.PHONY: install lint format typecheck test check

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest

check: lint typecheck test

.PHONY: db dbt-parse dagster simulate source-api load pipeline
db:
	docker compose up -d postgres

dbt-parse:
	uv run dbt parse --project-dir transform --profiles-dir transform

dagster:
	SOURCE_IN_PROCESS=1 uv run dagster dev

# Grow the fictional company's history: make simulate DAYS=30
DAYS ?= 30
simulate:
	uv run python -m saas_metrics simulate --days $(DAYS)

# Run the source billing API on http://localhost:8100
source-api:
	uv run python -m saas_metrics serve

# Incremental load into raw (no API server needed)
load:
	uv run python -m saas_metrics load --in-process

# Load, then build and test every dbt model
pipeline: load
	uv run dbt build --project-dir transform --profiles-dir transform
