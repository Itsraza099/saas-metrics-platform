{#
  Use the configured schema name as-is (staging, marts) instead of dbt's default of
  prefixing it with the target schema (analytics_staging). Other tools, like the read-only
  role in metrics-mcp-server, rely on these names being stable.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
