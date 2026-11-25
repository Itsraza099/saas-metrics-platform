select
    customer_id,
    name as customer_name,
    country as country_code,
    created_at::date as created_at
from {{ source('raw', 'customers') }}
