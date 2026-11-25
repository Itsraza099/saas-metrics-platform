"""Dagster entry point. Run `make dagster` and open http://localhost:3000.

Planned asset graph (see docs/decisions/0001):
    source API → raw tables (incremental, cursor-based) → dbt staging → dbt marts
"""

import dagster as dg

from saas_metrics.generator import generate


@dg.asset(
    description="Synthetic billing data; stands in for the source system until the API exists."
)
def synthetic_billing_data() -> dg.MaterializeResult[None]:
    ds = generate()
    return dg.MaterializeResult(
        metadata={
            "customers": len(ds.customers),
            "subscriptions": len(ds.subscriptions),
            "invoices": len(ds.invoices),
        }
    )


defs = dg.Definitions(assets=[synthetic_billing_data])
