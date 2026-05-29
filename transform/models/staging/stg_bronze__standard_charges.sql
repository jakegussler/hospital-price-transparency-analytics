select
    standard_charge_id,
    snapshot_id,
    charge_item_id,
    cast(charge_ordinal as integer) as charge_ordinal,
    {{ hpt_safe_decimal('minimum') }} as minimum,
    {{ hpt_safe_decimal('maximum') }} as maximum,
    {{ hpt_safe_decimal('gross_charge') }} as gross_charge,
    {{ hpt_safe_decimal('discounted_cash') }} as discounted_cash,
    setting as raw_setting,
    {{ hpt_clean_text('setting') }} as clean_setting,
    billing_class as raw_billing_class,
    {{ hpt_clean_text('billing_class') }} as clean_billing_class,
    additional_generic_notes
from {{ source('bronze', 'standard_charges') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
