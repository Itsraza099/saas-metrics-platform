with latest as ({{ latest_version(source('raw', 'customers')) }})

select
    payload ->> 'id' as customer_id,
    payload ->> 'name' as customer_name,
    payload ->> 'country' as country_code,
    (payload ->> 'created_at')::timestamptz as created_at,
    source_updated_at as updated_at,
    _loaded_at
from latest
