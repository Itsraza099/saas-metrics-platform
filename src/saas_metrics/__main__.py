"""Command line for local development.

python -m saas_metrics simulate --until 2025-11-30   # grow the source system's history
python -m saas_metrics serve                         # run the source API on :8100
python -m saas_metrics load                          # incremental load into raw
python -m saas_metrics load --in-process             # same, without a running API
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date, timedelta

import httpx

from saas_metrics.config import SOURCE_API_URL, SOURCE_DB, connect
from saas_metrics.load import load_all
from saas_metrics.source.api import create_app
from saas_metrics.source.simulator import Simulator


def _source_client(in_process: bool) -> httpx.Client:
    if in_process:
        import warnings

        warnings.filterwarnings("ignore", message=".*httpx2.*")  # starlette's notice, not ours
        from fastapi.testclient import TestClient

        return TestClient(create_app(SOURCE_DB))
    return httpx.Client(base_url=SOURCE_API_URL, timeout=30)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="saas_metrics")
    sub = parser.add_subparsers(dest="command", required=True)

    sim = sub.add_parser("simulate", help="advance the source system")
    group = sim.add_mutually_exclusive_group(required=True)
    group.add_argument("--days", type=int)
    group.add_argument("--until", type=date.fromisoformat)

    serve = sub.add_parser("serve", help="run the source API")
    serve.add_argument("--port", type=int, default=8100)

    load = sub.add_parser("load", help="incremental load into raw")
    load.add_argument("--in-process", action="store_true", help="call the API without a server")
    load.add_argument("--page-size", type=int, default=500)
    load.add_argument("--lookback-minutes", type=int, default=0)

    args = parser.parse_args(argv)

    if args.command == "simulate":
        sim_ = Simulator(SOURCE_DB)
        try:
            n = sim_.run_until(args.until) if args.until else sim_.run_days(args.days)
            print(f"Simulated {n} days; source is now at {sim_.last_day}")
        finally:
            sim_.close()
    elif args.command == "serve":
        import uvicorn

        uvicorn.run(create_app(SOURCE_DB), port=args.port)
    else:
        with connect() as conn, _source_client(args.in_process) as client:
            for s in load_all(
                conn,
                client,
                page_size=args.page_size,
                lookback=timedelta(minutes=args.lookback_minutes),
            ):
                print(
                    f"{s.resource:<14} pages {s.pages:>3}  fetched {s.fetched:>6}  "
                    f"new {s.inserted:>6}  already had {s.skipped:>6}  watermark {s.watermark}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
