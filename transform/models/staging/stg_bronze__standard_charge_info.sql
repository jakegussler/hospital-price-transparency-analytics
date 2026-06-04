select
    charge_item_id,
    snapshot_id,
    description as raw_description,
    {{ hpt_clean_text('description') }} as clean_description,
    cast(item_ordinal as integer) as item_ordinal,
    {{ hpt_bronze_column_or_null('standard_charge_info', 'reported_schema_version') }}
        as reported_schema_version,
    {{ hpt_bronze_column_or_null('standard_charge_info', 'reported_schema_family') }}
        as reported_schema_family,
    {{ hpt_bronze_column_or_null('standard_charge_info', 'parser_schema_family') }}
        as parser_schema_family,
    {{ hpt_bronze_column_or_null('standard_charge_info', 'parser_schema_version') }}
        as parser_schema_version,
    cast(
        {{ hpt_bronze_column_or_null(
            'standard_charge_info',
            'schema_version_mismatch',
            'boolean'
        ) }} as boolean
    ) as schema_version_mismatch
from {{ hpt_staging_source(source('bronze', 'standard_charge_info')) }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
