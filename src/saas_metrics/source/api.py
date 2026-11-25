"""The source system's HTTP API, modelled on how APIs like Stripe's list objects.

    GET /v1/{resource}?updated_since=2025-01-01T00:00:00Z&limit=500
    GET /v1/{resource}?cursor=<next_cursor from the previous page>&limit=500

Rows come back ordered by ``(updated_at, id)``. Paging uses a *keyset* cursor (the last
row's updated_at and id) rather than an offset, so rows changing mid-read can't make a page
skip or repeat anything. ``updated_since`` is inclusive: re-reading rows at the boundary is
harmless because the loader ignores versions it already has.
"""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

RESOURCES = ("customers", "subscriptions", "invoices")


def encode_cursor(updated_at: str, row_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([updated_at, row_id]).encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        updated_at, row_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, binascii.Error, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return str(updated_at), str(row_id)


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="Fictional billing API")

    @app.get("/v1/{resource}")
    def list_resource(
        resource: str,
        updated_since: str | None = None,
        cursor: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
    ) -> dict[str, Any]:
        if resource not in RESOURCES:
            raise HTTPException(status_code=404, detail=f"unknown resource {resource!r}")
        if cursor:
            after_ts, after_id = decode_cursor(cursor)
            where, params = "(updated_at, id) > (?, ?)", [after_ts, after_id]
        elif updated_since:
            where, params = "updated_at >= ?", [updated_since]
        else:
            where, params = "1 = 1", []

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"select * from {resource} where {where} order by updated_at, id limit ?",
                [*params, limit + 1],
            ).fetchall()
        finally:
            conn.close()

        data = [dict(r) for r in rows[:limit]]
        next_cursor = encode_cursor(data[-1]["updated_at"], data[-1]["id"]) if data else None
        return {"data": data, "has_more": len(rows) > limit, "next_cursor": next_cursor}

    return app
