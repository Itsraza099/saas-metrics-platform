select
    subscription_id,
    customer_id,
    plan as plan_name,
    quantity,
    started_at::date as started_at,
    ended_at::date as ended_at
from {{ source('raw', 'subscriptions') }}
