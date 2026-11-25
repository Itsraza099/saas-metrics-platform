"""Settings from environment variables (see .env.example), with local-dev defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DB = Path(os.environ.get("SOURCE_DB", PROJECT_ROOT / "data" / "source" / "billing.db"))
SOURCE_API_URL = os.environ.get("SOURCE_API_URL", "http://localhost:8100")
DBT_PROJECT_DIR = PROJECT_ROOT / "transform"


def connect() -> psycopg.Connection[Any]:
    """Connect to the warehouse using the standard PG* environment variables.

    autocommit=True matters: it makes each ``with conn.transaction():`` block a real,
    separately committed transaction. Without it they'd all be savepoints inside one big
    transaction, and "commit after every page" would silently stop being true.
    """
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        user=os.environ.get("PGUSER", "metrics"),
        password=os.environ.get("PGPASSWORD", "metrics"),
        dbname=os.environ.get("PGDATABASE", "metrics"),
        autocommit=True,
    )
