# 0001. Stack and data layers

- Status: Proposed
- Date: 2026-11-25

## Context
The goal is a realistic ELT pipeline for SaaS revenue metrics that shows layered
modelling, testing, incremental loading and orchestration.

## Decision
- **Source:** a simulated billing system (SQLite) that advances one day at a time, served
  by a small API with `updated_since` and cursor paging, so incremental loads have real
  changes to pick up. Deterministic: seeded by date, so history is reproducible.
- **Warehouse:** Postgres 16 (Docker locally).
- **Layers:** `raw` (loaded as-is) → `staging` (renamed, typed, one model per source table)
  → `marts` (facts and dimensions with a stated grain).
- **Transform:** dbt, with tests on every primary key and source freshness checks.
- **Orchestration:** Dagster software-defined assets, using `dagster-dbt` to put dbt
  models on the same asset graph.

## Alternatives considered
- Real Stripe test-mode data: realistic, but slow to build years of history. Used in
  revenue-recovery-engine instead, where signed webhooks matter.
- DuckDB: simpler to run, but has no database roles, and metrics-mcp-server needs a
  real read-only role.
- Airflow: the most common orchestrator, but task-based; Dagster's asset model maps
  directly onto dbt models and shows lineage for free.

## Consequences
Needs Docker (or a local Postgres). dbt and Dagster are heavy dependencies.
