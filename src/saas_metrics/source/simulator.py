"""A fictional SaaS company's billing system, simulated one day at a time.

This stands in for a real source system (think Stripe). It writes to its own SQLite
database, and rows really change over time: plans get upgraded, invoices move from
``failed`` to ``paid``, customers churn. That's what makes incremental loading worth doing.

Each day's randomness is seeded from (seed, date), so the history is identical whether you
simulate 60 days in one go or in two runs of 30. Tests rely on this.

Billing model (kept deliberately simple):
- Calendar billing: every active subscription is invoiced on the 1st of the month for
  ``price x quantity``. No proration.
- Failed payments are retried daily; after ``max_retry_days`` the invoice becomes
  ``uncollectible`` and the subscription is cancelled (involuntary churn).
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

PLANS: dict[str, int] = {"starter": 2_900, "growth": 9_900, "scale": 29_900}  # pence/seat/month
PLAN_ORDER = ["starter", "growth", "scale"]
COUNTRIES = ["GB", "GB", "GB", "IE", "DE", "FR", "NL", "US"]
NAME_PARTS = (
    ["Acme", "Bright", "Cobalt", "Delta", "Ember", "Fable", "Granite", "Harbour", "Indigo"],
    ["Labs", "Systems", "Studio", "Works", "Analytics", "Logistics", "Health", "Foods"],
)

SCHEMA = """
create table if not exists customers (
    id text primary key, name text not null, country text not null,
    created_at text not null, updated_at text not null
);
create table if not exists subscriptions (
    id text primary key, customer_id text not null references customers (id),
    plan text not null, quantity integer not null, status text not null,
    started_at text not null, ended_at text, updated_at text not null
);
create table if not exists invoices (
    id text primary key, subscription_id text not null references subscriptions (id),
    customer_id text not null, period_start text not null, amount_pence integer not null,
    status text not null, attempts integer not null,
    created_at text not null, updated_at text not null
);
create table if not exists sim_state (key text primary key, value text not null);
create index if not exists customers_updated on customers (updated_at, id);
create index if not exists subscriptions_updated on subscriptions (updated_at, id);
create index if not exists invoices_updated on invoices (updated_at, id);
"""


@dataclass(frozen=True)
class SimConfig:
    start: date = date(2024, 1, 1)
    seed: int = 42
    signup_trials: int = 4  # each day: this many chances of a new customer...
    signup_probability: float = 0.15  # ...each with this probability (mean 0.6/day)
    daily_churn: float = 0.0012
    daily_change: float = 0.004  # chance an active subscription changes seats or plan
    daily_rename: float = 0.0004  # chance a customer's details change
    failure_rate: float = 0.05
    retry_success: float = 0.2
    max_retry_days: int = 14


class _Clock:
    """Hands out strictly increasing timestamps within one simulated day."""

    def __init__(self, day: date, rng: random.Random) -> None:
        self._now = datetime.combine(day, time(0, 0), tzinfo=UTC)
        self._rng = rng

    def tick(self) -> str:
        self._now += timedelta(seconds=self._rng.randint(1, 30))
        return self._now.strftime("%Y-%m-%dT%H:%M:%SZ")


class Simulator:
    def __init__(self, db_path: Path, config: SimConfig | None = None) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.config = config or SimConfig()

    def close(self) -> None:
        self.conn.close()

    # --- state -------------------------------------------------------------------------

    def _get(self, key: str) -> str | None:
        row = self.conn.execute("select value from sim_state where key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def _set(self, key: str, value: str) -> None:
        self.conn.execute(
            "insert into sim_state (key, value) values (?, ?) "
            "on conflict (key) do update set value = excluded.value",
            (key, value),
        )

    def _next_id(self, prefix: str) -> str:
        n = int(self._get(f"seq_{prefix}") or 0) + 1
        self._set(f"seq_{prefix}", str(n))
        return f"{prefix}_{n:06d}"

    @property
    def last_day(self) -> date | None:
        value = self._get("last_day")
        return date.fromisoformat(value) if value else None

    # --- running -----------------------------------------------------------------------

    def run_until(self, end: date) -> int:
        """Simulate every day up to and including ``end``. Returns days simulated."""
        day = (self.last_day + timedelta(days=1)) if self.last_day else self.config.start
        count = 0
        while day <= end:
            with self.conn:  # one transaction per day: a crash never leaves half a day
                self._simulate_day(day)
                self._set("last_day", day.isoformat())
            day += timedelta(days=1)
            count += 1
        return count

    def run_days(self, days: int) -> int:
        start = (self.last_day + timedelta(days=1)) if self.last_day else self.config.start
        return self.run_until(start + timedelta(days=days - 1))

    def _simulate_day(self, day: date) -> None:
        rng = random.Random(f"{self.config.seed}-{day.isoformat()}")
        clock = _Clock(day, rng)
        self._retry_failed_invoices(day, rng, clock)
        if day.day == 1:
            self._invoice_active_subscriptions(day, rng, clock)
        self._change_subscriptions(day, rng, clock)
        self._rename_customers(rng, clock)
        self._sign_up_customers(day, rng, clock)

    # --- daily events ------------------------------------------------------------------

    def _retry_failed_invoices(self, day: date, rng: random.Random, clock: _Clock) -> None:
        failed = self.conn.execute(
            "select id, subscription_id, attempts, created_at from invoices "
            "where status = 'failed' order by id"
        ).fetchall()
        for invoice_id, sub_id, attempts, created_at in failed:
            age = (day - date.fromisoformat(created_at[:10])).days
            if rng.random() < self.config.retry_success:
                status = "paid"
            elif age >= self.config.max_retry_days:
                status = "uncollectible"
            else:
                status = "failed"
            ts = clock.tick()
            self.conn.execute(
                "update invoices set status = ?, attempts = ?, updated_at = ? where id = ?",
                (status, attempts + 1, ts, invoice_id),
            )
            if status == "uncollectible":
                self.conn.execute(
                    "update subscriptions set status = 'cancelled', ended_at = ?, updated_at = ? "
                    "where id = ? and status = 'active'",
                    (day.isoformat(), clock.tick(), sub_id),
                )

    def _invoice_active_subscriptions(self, day: date, rng: random.Random, clock: _Clock) -> None:
        subs = self.conn.execute(
            "select id, customer_id, plan, quantity from subscriptions "
            "where status = 'active' order by id"
        ).fetchall()
        for sub_id, customer_id, plan, quantity in subs:
            status = "failed" if rng.random() < self.config.failure_rate else "paid"
            ts = clock.tick()
            self.conn.execute(
                "insert into invoices values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._next_id("in"),
                    sub_id,
                    customer_id,
                    day.isoformat(),
                    PLANS[plan] * quantity,
                    status,
                    1,
                    ts,
                    ts,
                ),
            )

    def _change_subscriptions(self, day: date, rng: random.Random, clock: _Clock) -> None:
        subs = self.conn.execute(
            "select id, plan, quantity from subscriptions where status = 'active' order by id"
        ).fetchall()
        for sub_id, plan, quantity in subs:
            roll = rng.random()
            if roll < self.config.daily_churn:
                self.conn.execute(
                    "update subscriptions set status = 'cancelled', ended_at = ?, updated_at = ? "
                    "where id = ?",
                    (day.isoformat(), clock.tick(), sub_id),
                )
            elif roll < self.config.daily_churn + self.config.daily_change:
                if rng.random() < 0.7:  # seats change; growth is more likely than shrinkage
                    quantity = max(1, quantity + rng.choice([-2, -1, 1, 1, 2, 3]))
                else:  # move one plan up or down
                    i = PLAN_ORDER.index(plan) + rng.choice([-1, 1, 1])
                    plan = PLAN_ORDER[min(max(i, 0), len(PLAN_ORDER) - 1)]
                self.conn.execute(
                    "update subscriptions set plan = ?, quantity = ?, updated_at = ? where id = ?",
                    (plan, quantity, clock.tick(), sub_id),
                )

    def _rename_customers(self, rng: random.Random, clock: _Clock) -> None:
        ids = [r[0] for r in self.conn.execute("select id from customers order by id")]
        for customer_id in ids:
            if rng.random() < self.config.daily_rename:
                self.conn.execute(
                    "update customers set country = ?, updated_at = ? where id = ?",
                    (rng.choice(COUNTRIES), clock.tick(), customer_id),
                )

    def _sign_up_customers(self, day: date, rng: random.Random, clock: _Clock) -> None:
        signups = sum(
            rng.random() < self.config.signup_probability for _ in range(self.config.signup_trials)
        )
        for _ in range(signups):
            customer_id = self._next_id("cus")
            name = f"{rng.choice(NAME_PARTS[0])} {rng.choice(NAME_PARTS[1])}"
            ts = clock.tick()
            self.conn.execute(
                "insert into customers values (?, ?, ?, ?, ?)",
                (customer_id, name, rng.choice(COUNTRIES), ts, ts),
            )
            ts = clock.tick()
            self.conn.execute(
                "insert into subscriptions values (?, ?, ?, ?, 'active', ?, null, ?)",
                (
                    self._next_id("sub"),
                    customer_id,
                    rng.choices(PLAN_ORDER, weights=[6, 3, 1])[0],
                    rng.randint(1, 10),
                    day.isoformat(),
                    ts,
                ),
            )
