import sqlite3
from datetime import date
from pathlib import Path

from saas_metrics.source.simulator import PLANS, SimConfig, Simulator

CONFIG = SimConfig(start=date(2025, 1, 1), signup_probability=0.5)


def _dump(db: Path) -> dict[str, list[tuple[object, ...]]]:
    conn = sqlite3.connect(db)
    try:
        return {
            t: conn.execute(f"select * from {t} order by id").fetchall()
            for t in ("customers", "subscriptions", "invoices")
        }
    finally:
        conn.close()


def test_history_is_the_same_however_it_is_chunked(tmp_path: Path) -> None:
    one_go = Simulator(tmp_path / "a.db", CONFIG)
    one_go.run_days(70)
    one_go.close()
    chunked = Simulator(tmp_path / "b.db", CONFIG)
    chunked.run_days(30)
    chunked.run_days(40)
    chunked.close()
    assert _dump(tmp_path / "a.db") == _dump(tmp_path / "b.db")


def test_run_until_is_inclusive_and_resumable(tmp_path: Path) -> None:
    sim = Simulator(tmp_path / "s.db", CONFIG)
    assert sim.last_day is None
    assert sim.run_until(date(2025, 1, 10)) == 10
    assert sim.last_day == date(2025, 1, 10)
    assert sim.run_until(date(2025, 1, 10)) == 0  # nothing left to do
    sim.close()


def test_invariants(source: Simulator) -> None:
    conn = source.conn
    # every row's updated_at is at or after its creation
    assert not conn.execute("select 1 from customers where updated_at < created_at").fetchall()
    assert not conn.execute("select 1 from invoices where updated_at < created_at").fetchall()
    # cancelled subscriptions have an end date, active ones don't
    assert not conn.execute(
        "select 1 from subscriptions where (status = 'cancelled') != (ended_at is not null)"
    ).fetchall()
    # invoice amounts are a whole number of seats at a real plan price
    for (amount,) in conn.execute("select amount_pence from invoices"):
        assert any(amount % price == 0 for price in PLANS.values())
    # invoices only exist for the 1st of the month
    assert {r[0][8:] for r in conn.execute("select period_start from invoices")} == {"01"}
