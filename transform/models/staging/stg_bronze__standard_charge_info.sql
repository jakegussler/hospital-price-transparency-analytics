select
    charge_item_id,
    snapshot_id,
    description as raw_description,
    {{ hpt_clean_text('description') }} as clean_description,
    cast(item_ordinal as integer) as item_ordinal,
    reported_schema_version,
    reported_schema_family,
    parser_schema_family,
    parser_schema_version,
    cast(schema_version_mismatch as boolean) as schema_version_mismatch
from {{ source('bronze', 'standard_charge_info') }}
