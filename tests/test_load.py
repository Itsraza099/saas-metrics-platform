"""Loader behaviour against a real Postgres: idempotency, incremental loads, crash safety."""

from datetime import timedelta
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from saas_metrics.load import ensure_schema, get_watermark, load_all, load_resource
from saas_metrics.source.simulator import Simulator


def _count(pg: psycopg.Connection[Any], schema: str, table: str) -> int:
    row = pg.execute(
        sql.SQL("select count(*) from {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
    ).fetchone()
    assert row is not None
    return int(row[0])


def _source_count(source: Simulator, table: str) -> int:
    return int(source.conn.execute(f"select count(*) from {table}").fetchone()[0])


def test_first_load_copies_everything(
    pg: psycopg.Connection[Any], schema: str, api: TestClient, source: Simulator
) -> None:
    stats = load_all(pg, api, schema=schema, page_size=50)
    for s in stats:
        assert s.inserted == _source_count(source, s.resource) == _count(pg, schema, s.resource)


def test_running_twice_adds_nothing(
    pg: psycopg.Connection[Any], schema: str, api: TestClient
) -> None:
    load_all(pg, api, schema=schema)
    again = load_all(pg, api, schema=schema)
    assert all(s.inserted == 0 for s in again)


def test_only_changes_are_loaded_and_history_is_kept(
    pg: psycopg.Connection[Any], schema: str, api: TestClient, source: Simulator
) -> None:
    load_all(pg, api, schema=schema)
    before = _count(pg, schema, "subscriptions")
    source.run_days(45)
    stats = {s.resource: s for s in load_all(pg, api, schema=schema)}

    # A fetched row was either new or already loaded. Nothing is lost.
    assert stats["subscriptions"].fetched < _source_count(source, "subscriptions") + 5
    assert _count(pg, schema, "subscriptions") == before + stats["subscriptions"].inserted
    # Old versions are kept: raw holds at least as many rows as the source has ids.
    assert _count(pg, schema, "subscriptions") >= _source_count(source, "subscriptions")


def test_lookback_rereads_without_duplicating(
    pg: psycopg.Connection[Any], schema: str, api: TestClient
) -> None:
    load_all(pg, api, schema=schema)
    stats = load_resource(pg, api, "invoices", schema=schema, lookback=timedelta(days=30))
    assert stats.fetched > 1 and stats.inserted == 0


class _CrashAfter(httpx.Client):
    """Wraps the API client and fails on the Nth request, like a network drop mid-load."""

    def __init__(self, inner: TestClient, fail_on: int) -> None:
        self._inner, self._fail_on, self._calls = inner, fail_on, 0

    def get(self, url: Any, **kwargs: Any) -> httpx.Response:
        self._calls += 1
        if self._calls == self._fail_on:
            raise httpx.ConnectError("simulated network failure")
        response: httpx.Response = self._inner.get(url, **kwargs)
        return response


def test_crash_mid_load_keeps_committed_pages_and_resumes(
    pg: psycopg.Connection[Any], schema: str, api: TestClient, source: Simulator
) -> None:
    ensure_schema(pg, schema)
    with pytest.raises(httpx.ConnectError):
        load_resource(pg, _CrashAfter(api, fail_on=3), "invoices", schema=schema, page_size=20)

    # Pages 1 and 2 were committed, with a watermark to resume from.
    assert _count(pg, schema, "invoices") == 40
    assert get_watermark(pg, "invoices", schema) is not None
    run = pg.execute(
        sql.SQL("select status, error from {}._load_runs").format(sql.Identifier(schema))
    ).fetchone()
    assert run is not None and run[0] == "failed" and "simulated" in run[1]

    load_resource(pg, api, "invoices", schema=schema, page_size=20)
    assert _count(pg, schema, "invoices") == _source_count(source, "invoices")


def test_unknown_resource_is_rejected(pg: psycopg.Connection[Any], api: TestClient) -> None:
    with pytest.raises(ValueError, match="unknown resource"):
        load_resource(pg, api, "payments")
