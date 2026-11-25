"""Dagster definitions. Run `make dagster` and open http://localhost:3000.

Asset graph:

    raw/customers ─┐
    raw/subscriptions ─┼─> dbt: stg_* (and, later, marts)
    raw/invoices ──┘

The raw assets are keyed ["raw", <table>] on purpose: that's the key dagster-dbt gives the
dbt source `raw.<table>`, so Dagster links each load to the models that read it without any
extra mapping. A daily schedule materialises everything.
"""

# No `from __future__ import annotations` here: Dagster inspects the type hints at runtime.
import os
from collections.abc import Iterator
from typing import Any

import dagster as dg
import httpx
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from saas_metrics.config import DBT_PROJECT_DIR, SOURCE_API_URL, SOURCE_DB, connect
from saas_metrics.load import ensure_schema, load_resource
from saas_metrics.source.api import RESOURCES, create_app

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()  # in `dagster dev`, (re)build the manifest on startup


def _source_client() -> httpx.Client:
    # SOURCE_IN_PROCESS=1 calls the API app directly, so local runs and CI don't need a server.
    if os.environ.get("SOURCE_IN_PROCESS") == "1":
        from fastapi.testclient import TestClient

        return TestClient(create_app(SOURCE_DB))
    return httpx.Client(base_url=SOURCE_API_URL, timeout=30)


def _raw_asset(resource: str) -> dg.AssetsDefinition:
    @dg.asset(
        name=resource,
        key_prefix="raw",
        group_name="extract_load",
        kinds={"python", "postgres"},
        description=f"Append-only versions of source `{resource}`, loaded incrementally.",
    )
    def _load(context: dg.AssetExecutionContext) -> dg.MaterializeResult[Any]:
        with connect() as conn, _source_client() as client:
            ensure_schema(conn)
            stats = load_resource(conn, client, resource)
        context.log.info(
            f"{resource}: {stats.inserted} new versions, {stats.skipped} already loaded"
        )
        return dg.MaterializeResult(
            metadata={
                "pages": stats.pages,
                "fetched": stats.fetched,
                "inserted": stats.inserted,
                "already_loaded": stats.skipped,
                "watermark": str(stats.watermark),
            }
        )

    return _load


raw_assets = [_raw_asset(r) for r in RESOURCES]


@dbt_assets(manifest=dbt_project.manifest_path)
def dbt_models(context: dg.AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    yield from dbt.cli(["build"], context=context).stream()


daily_refresh = dg.ScheduleDefinition(
    name="daily_refresh",
    target=dg.AssetSelection.all(),
    cron_schedule="0 6 * * *",
    execution_timezone="Europe/London",
)

defs = dg.Definitions(
    assets=[*raw_assets, dbt_models],
    schedules=[daily_refresh],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
