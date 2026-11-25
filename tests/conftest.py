"""Shared fixtures.

Loader tests need Postgres. Each test gets its own throwaway schema, so tests never touch
the real `raw` schema and can run in parallel. Locally they're skipped if Postgres isn't
running; in CI, REQUIRE_DB=1 turns that skip into a failure so they can't silently not run.
"""

import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from saas_metrics.config import connect
from saas_metrics.source.api import create_app
from saas_metrics.source.simulator import SimConfig, Simulator

SMALL = SimConfig(start=date(2025, 1, 1), signup_probability=0.5)


@pytest.fixture
def source(tmp_path: Path) -> Iterator[Simulator]:
    sim = Simulator(tmp_path / "billing.db", SMALL)
    sim.run_days(60)
    yield sim
    sim.close()


@pytest.fixture
def api(source: Simulator, tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "billing.db"))


@pytest.fixture
def pg() -> Iterator[psycopg.Connection[Any]]:
    try:
        conn = connect()
    except psycopg.OperationalError:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip("Postgres not running (start it with `make db`)")
    yield conn
    conn.close()


@pytest.fixture
def schema(pg: psycopg.Connection[Any]) -> Iterator[str]:
    name = f"raw_test_{uuid.uuid4().hex[:8]}"
    yield name
    pg.execute(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(name)))
