# Marts (planned)

| Model | Grain (one row = …) | Purpose |
|---|---|---|
| `dim_customers` | customer | Attributes, history kept with a dbt snapshot (SCD type 2) |
| `fct_mrr_monthly` | customer × month | MRR with new / expansion / contraction / churn movements |
| `fct_revenue_kpis_monthly` | month | MRR, ARR, NRR, GRR, ARPA |
| `fct_cohort_retention` | signup cohort × months since signup | Logo and revenue retention |
