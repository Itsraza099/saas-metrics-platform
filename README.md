# SaaS Metrics Platform

**The revenue numbers a SaaS finance team reports on, built the way a data team would.**
An ELT pipeline that turns raw billing data into tested, documented **MRR, ARR, NRR, GRR,
ARPA and cohort retention**.

[![CI](https://github.com/Itsraza099/saas-metrics-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Itsraza099/saas-metrics-platform/actions/workflows/ci.yml)
![dbt](https://img.shields.io/badge/dbt-1.x-FF694B)
![Dagster](https://img.shields.io/badge/Dagster-assets-4F43DD)
![Postgres](https://img.shields.io/badge/Postgres-16-336791)

<!-- Add here once built: link to dbt docs (lineage graph) on GitHub Pages, and a dashboard screenshot. -->

| | |
|---|---|
| **Problem** | Revenue metrics computed ad hoc in spreadsheets disagree with each other and nobody can say why. |
| **Solution** | One pipeline with layered models, a stated grain for every table, and tests that fail before bad numbers reach a report. |
| **Shows** | ELT, incremental loads with cursors, dimensional modelling, slowly changing dimensions, data contracts, freshness checks, orchestration |
| **Stack** | Python · dbt · Dagster · Postgres · Docker · GitHub Actions |

## Architecture

```mermaid
flowchart LR
    G[Billing source<br/>synthetic SaaS company] --> API[Source API<br/>updated_since paging]
    API -->|incremental load,<br/>cursor per table| RAW[(raw)]
    RAW -->|dbt| STG[(staging)]
    STG -->|dbt| MARTS[(marts<br/>MRR · NRR · cohorts)]
    D{{Dagster}} -.orchestrates.-> API & RAW & STG & MARTS
    MARTS --> MCP[AI assistant via<br/>metrics-mcp-server]
```

| Layer | What happens | Example |
|---|---|---|
| `raw` | Loaded exactly as received, never edited | `raw.invoices` |
| `staging` | Renamed, typed, one model per source table, tested | `stg_invoices` |
| `marts` | Facts and dimensions, each with a stated grain | `fct_mrr_monthly`: one row per customer per month |

## Engineering highlights

- **Every table states its grain** (what one row means), and its primary key is tested for
  uniqueness and nulls. ([staging tests](transform/models/staging/_staging.yml))
- **Source freshness checks** warn after 24 hours without new data and fail after 48.
- **Customer history is preserved** *(in progress)* with dbt snapshots (slowly changing
  dimension type 2), so last year's MRR still adds up after a customer changes plan.
- **Deterministic source data.** The generator is seeded, so every test run and demo sees the
  same company. ([generator](src/saas_metrics/generator.py))
- **Why dbt + Dagster + Postgres** and not Airflow or DuckDB:
  [decision 0001](docs/decisions/0001-stack-and-layers.md).

## Proving it's correct

| Break it on purpose | What catches it | Status |
|---|---|---|
| Run the same load twice | Row counts don't change (idempotent loads) | planned |
| Insert a duplicate customer into `raw` | dbt `unique` test fails the run | test written |
| Stop loading for two days | Source freshness check errors | check configured |
| Rename a column upstream | Model contract fails before marts are touched | planned |

## Build progress

- [x] Seeded billing data generator with grain tests
- [x] dbt staging layer with tests and freshness checks
- [x] Dagster project wired up, CI green
- [ ] Source API with cursor-based incremental loads
- [ ] Marts: `fct_mrr_monthly`, `fct_revenue_kpis_monthly`, `fct_cohort_retention`, `dim_customers`
- [ ] dbt docs and metrics dashboard published to GitHub Pages

## How I worked

Each choice has a [decision record](docs/decisions/); the [glossary](docs/glossary.md) is my
own explanation of each concept with examples from this repo.

**Part of a portfolio:** [metrics-mcp-server](https://github.com/Itsraza099/metrics-mcp-server)
lets an AI assistant query these marts through a read-only role. See all projects on
[my profile](https://github.com/Itsraza099).

<details>
<summary><b>Run locally</b></summary>

Needs [uv](https://docs.astral.sh/uv/) and Docker.

```bash
cp .env.example .env
make install
make db          # start Postgres
make dbt-parse   # check the dbt project compiles
make dagster     # open http://localhost:3000
make check       # lint, type check, tests
```
</details>
