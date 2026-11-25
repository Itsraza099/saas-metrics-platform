select
    invoice_id,
    subscription_id,
    customer_id,
    period_start::date as period_start,
    amount_pence,
    status
from {{ source('raw', 'invoices') }}
