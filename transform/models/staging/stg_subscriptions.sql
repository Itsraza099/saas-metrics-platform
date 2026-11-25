with latest as ({{ latest_version(source('raw', 'subscriptions')) }})

select
    payload ->> 'id' as subscription_id,
    payload ->> 'customer_id' as customer_id,
    payload ->> 'plan' as plan_name,
    (payload ->> 'quantity')::int as quantity,
    payload ->> 'status' as status,
    (payload ->> 'started_at')::date as started_at,
    (payload ->> 'ended_at')::date as ended_at,
    source_updated_at as updated_at,
    _loaded_at
from latest
