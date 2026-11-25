{#
  raw keeps every version of every row (append-only). Staging wants the current state:
  the version with the newest source_updated_at for each id.
#}
{% macro latest_version(source_relation) %}
    select payload, source_updated_at, _loaded_at
    from (
        select
            *,
            row_number() over (partition by id order by source_updated_at desc) as version_rank
        from {{ source_relation }}
    ) ranked
    where version_rank = 1
{% endmacro %}
