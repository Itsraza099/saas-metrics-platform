"""Incremental extract-load from the source API into Postgres ``raw`` tables.

How it stays correct:

- **Append-only raw.** Every version of every row is kept, keyed on ``(id,
  source_updated_at)``. Nothing in raw is ever updated or deleted, so history is never lost
  and dbt can rebuild anything downstream from it.
- **Idempotent.** Inserting a version that's already there does nothing (``on conflict do
  nothing``). Running the same load twice, or re-reading overlapping pages, can't create
  duplicates.
- **Watermark per resource.** ``raw._load_state`` remembers the latest ``updated_at``
  loaded. The next run asks the API for rows updated since then (minus an optional lookback,
  for sources whose timestamps can arrive slightly late).
- **Commit per page.** Each page's rows and the new watermark are committed in one
  transaction. If the run crashes on page 7, pages 1-6 are safely stored and the next run
  carries on from there.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
import psycopg
from psycopg import sql

from saas_metrics.source.api import RESOURCES


@dataclass(frozen=True)
class LoadStats:
    resource: str
    pages: int
    fetched: int
    inserted: int
    watermark: datetime | None

    @property
    def skipped(self) -> int:
        """Rows fetched that were already in raw (re-reads at the boundary, lookback, retries)."""
        return self.fetched - self.inserted


def ensure_schema(conn: psycopg.Connection[Any], schema: str = "raw") -> None:
    s = sql.Identifier(schema)
    with conn.transaction():
        conn.execute(sql.SQL("create schema if not exists {}").format(s))
        for resource in RESOURCES:
            conn.execute(
                sql.SQL(
                    """create table if not exists {}.{} (
                        id text not null,
                        source_updated_at timestamptz not null,
                        payload jsonb not null,
                        _batch_id uuid not null,
                        _loaded_at timestamptz not null default now(),
                        primary key (id, source_updated_at)
                    )"""
                ).format(s, sql.Identifier(resource))
            )
        conn.execute(
            sql.SQL(
                """create table if not exists {}._load_state (
                    resource text primary key,
                    watermark timestamptz not null,
                    updated_at timestamptz not null default now()
                )"""
            ).format(s)
        )
        conn.execute(
            sql.SQL(
                """create table if not exists {}._load_runs (
                    batch_id uuid primary key,
                    resource text not null,
                    started_at timestamptz not null default now(),
                    finished_at timestamptz,
                    status text not null,
                    pages int not null default 0,
                    fetched int not null default 0,
                    inserted int not null default 0,
                    error text
                )"""
            ).format(s)
        )


def get_watermark(
    conn: psycopg.Connection[Any], resource: str, schema: str = "raw"
) -> datetime | None:
    row = conn.execute(
        sql.SQL("select watermark from {}._load_state where resource = %s").format(
            sql.Identifier(schema)
        ),
        (resource,),
    ).fetchone()
    return None if row is None else row[0]


def load_resource(
    conn: psycopg.Connection[Any],
    client: httpx.Client,
    resource: str,
    *,
    page_size: int = 500,
    lookback: timedelta = timedelta(0),
    schema: str = "raw",
) -> LoadStats:
    """Load everything new for one resource. Safe to re-run at any time."""
    if resource not in RESOURCES:
        raise ValueError(f"unknown resource {resource!r}")
    s, table = sql.Identifier(schema), sql.Identifier(resource)
    batch_id = uuid.uuid4()
    pages = fetched = inserted = 0

    with conn.transaction():
        conn.execute(
            sql.SQL(
                "insert into {}._load_runs (batch_id, resource, status) values (%s, %s, 'running')"
            ).format(s),
            (batch_id, resource),
        )

    watermark = get_watermark(conn, resource, schema)
    params: dict[str, str | int] = {"limit": page_size}
    if watermark is not None:
        params["updated_since"] = (watermark - lookback).isoformat()

    try:
        while True:
            response = client.get(f"/v1/{resource}", params=params)
            response.raise_for_status()
            body = response.json()
            rows: list[dict[str, Any]] = body["data"]
            pages += 1
            fetched += len(rows)

            if rows:
                with conn.transaction():  # rows and watermark commit together, or not at all
                    cur = conn.execute(
                        sql.SQL(
                            """insert into {}.{} (id, source_updated_at, payload, _batch_id)
                               select r->>'id', (r->>'updated_at')::timestamptz, r, %s
                               from jsonb_array_elements(%s::jsonb) as r
                               on conflict (id, source_updated_at) do nothing"""
                        ).format(s, table),
                        (batch_id, json.dumps(rows)),
                    )
                    inserted += cur.rowcount
                    conn.execute(
                        sql.SQL(
                            """insert into {}._load_state (resource, watermark)
                               values (%s, %s::timestamptz)
                               on conflict (resource) do update
                               set watermark = greatest(
                                   {}._load_state.watermark, excluded.watermark
                               ),
                                   updated_at = now()"""
                        ).format(s, s),
                        (resource, rows[-1]["updated_at"]),
                    )

            if not body["has_more"]:
                break
            params = {"limit": page_size, "cursor": body["next_cursor"]}
    except Exception as exc:
        _finish_run(conn, schema, batch_id, "failed", pages, fetched, inserted, repr(exc))
        raise

    _finish_run(conn, schema, batch_id, "succeeded", pages, fetched, inserted, None)
    return LoadStats(resource, pages, fetched, inserted, get_watermark(conn, resource, schema))


def _finish_run(
    conn: psycopg.Connection[Any],
    schema: str,
    batch_id: uuid.UUID,
    status: str,
    pages: int,
    fetched: int,
    inserted: int,
    error: str | None,
) -> None:
    with conn.transaction():
        conn.execute(
            sql.SQL(
                """update {}._load_runs set finished_at = now(), status = %s,
                   pages = %s, fetched = %s, inserted = %s, error = %s where batch_id = %s"""
            ).format(sql.Identifier(schema)),
            (status, pages, fetched, inserted, error, batch_id),
        )


def load_all(
    conn: psycopg.Connection[Any], client: httpx.Client, *, schema: str = "raw", **kwargs: Any
) -> list[LoadStats]:
    ensure_schema(conn, schema)
    return [load_resource(conn, client, r, schema=schema, **kwargs) for r in RESOURCES]
