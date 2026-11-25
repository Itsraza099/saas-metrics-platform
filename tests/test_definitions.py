"""Dagster wiring. Needs the dbt manifest (`make dbt-parse`), which CI builds first."""

from saas_metrics.definitions import defs


def test_each_load_feeds_its_staging_model() -> None:
    graph = defs.resolve_asset_graph()
    for table in ("customers", "subscriptions", "invoices"):
        staging = graph.get(
            next(k for k in graph.get_all_asset_keys() if k.path[-1] == f"stg_{table}")
        )
        assert [p.to_user_string() for p in staging.parent_keys] == [f"raw/{table}"]


def test_daily_schedule_exists() -> None:
    assert defs.resolve_schedule_def("daily_refresh").cron_schedule == "0 6 * * *"
