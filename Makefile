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

.PHONY: db dbt-parse dagster
db:
	docker compose up -d postgres

dbt-parse:
	uv run dbt parse --project-dir transform --profiles-dir transform

dagster:
	uv run dagster dev
