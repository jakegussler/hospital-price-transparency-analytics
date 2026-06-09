select
    snapshot_id,
    charge_item_id,
    {{ hpt_safe_double('unit') }} as drug_unit,
    type as raw_drug_unit_type,
    {{ hpt_normalize_text('type') }} as clean_drug_unit_type
from {{ source('bronze', 'drug_information') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
