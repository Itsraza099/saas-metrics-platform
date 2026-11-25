with latest as ({{ latest_version(source('raw', 'invoices')) }})

select
    payload ->> 'id' as invoice_id,
    payload ->> 'subscription_id' as subscription_id,
    payload ->> 'customer_id' as customer_id,
    (payload ->> 'period_start')::date as period_start,
    (payload ->> 'amount_pence')::int as amount_pence,
    payload ->> 'status' as status,
    (payload ->> 'attempts')::int as attempts,
    (payload ->> 'created_at')::timestamptz as created_at,
    source_updated_at as updated_at,
    _loaded_at
from latest
