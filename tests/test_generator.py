"""Checks that the generated data respects its own grain and business rules."""

from saas_metrics.generator import PLANS, generate


def test_same_seed_same_data() -> None:
    assert generate(seed=7) == generate(seed=7)


def test_primary_keys_are_unique() -> None:
    ds = generate()
    assert len({c.customer_id for c in ds.customers}) == len(ds.customers)
    assert len({s.subscription_id for s in ds.subscriptions}) == len(ds.subscriptions)
    assert len({i.invoice_id for i in ds.invoices}) == len(ds.invoices)


def test_invoices_fall_inside_their_subscription() -> None:
    ds = generate()
    subs = {s.subscription_id: s for s in ds.subscriptions}
    for inv in ds.invoices:
        sub = subs[inv.subscription_id]
        assert inv.period_start >= sub.started_at
        assert sub.ended_at is None or inv.period_start < sub.ended_at


def test_invoice_amount_matches_plan_price() -> None:
    ds = generate()
    subs = {s.subscription_id: s for s in ds.subscriptions}
    for inv in ds.invoices:
        sub = subs[inv.subscription_id]
        assert inv.amount_pence == PLANS[sub.plan] * sub.quantity


def test_dagster_definitions_load() -> None:
    from saas_metrics.definitions import defs

    assert defs.resolve_asset_graph().get_all_asset_keys()
