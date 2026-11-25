"""Generate a fictional SaaS company's billing history.

Deterministic: the same seed always produces the same data, so tests and demos
are repeatable. Grain of each table:

- customers:      one row per customer
- subscriptions:  one row per subscription (a customer can have several over time)
- invoices:       one row per monthly invoice for a subscription
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

PLANS: dict[str, int] = {"starter": 2_900, "growth": 9_900, "scale": 29_900}  # pence per month
COUNTRIES = ["GB", "IE", "DE", "FR", "NL", "US"]


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    country: str
    created_at: date


@dataclass(frozen=True)
class Subscription:
    subscription_id: str
    customer_id: str
    plan: str
    quantity: int
    started_at: date
    ended_at: date | None


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    subscription_id: str
    customer_id: str
    period_start: date
    amount_pence: int
    status: str  # "paid" | "failed"


@dataclass
class Dataset:
    customers: list[Customer] = field(default_factory=list)
    subscriptions: list[Subscription] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def generate(
    n_customers: int = 200,
    start: date = date(2024, 1, 1),
    months: int = 24,
    seed: int = 42,
    monthly_churn: float = 0.03,
    payment_failure_rate: float = 0.04,
) -> Dataset:
    """Build customers, their subscriptions and monthly invoices."""
    rng = random.Random(seed)
    ds = Dataset()
    for i in range(1, n_customers + 1):
        signup = _add_months(start, rng.randrange(months))
        cust = Customer(f"cus_{i:05d}", f"Customer {i}", rng.choice(COUNTRIES), signup)
        ds.customers.append(cust)

        plan = rng.choice(list(PLANS))
        quantity = rng.randint(1, 10)
        month = signup
        end = _add_months(start, months)
        ended: date | None = None
        invoice_months: list[date] = []
        while month < end:
            invoice_months.append(month)
            if rng.random() < monthly_churn:
                ended = _add_months(month, 1)
                break
            month = _add_months(month, 1)

        sub = Subscription(f"sub_{i:05d}", cust.customer_id, plan, quantity, signup, ended)
        ds.subscriptions.append(sub)
        for n, period in enumerate(invoice_months, start=1):
            status = "failed" if rng.random() < payment_failure_rate else "paid"
            ds.invoices.append(
                Invoice(
                    f"in_{i:05d}_{n:03d}",
                    sub.subscription_id,
                    cust.customer_id,
                    period,
                    PLANS[plan] * quantity,
                    status,
                )
            )
    return ds
