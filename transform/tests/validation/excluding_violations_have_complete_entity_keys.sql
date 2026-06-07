select *
from {{ ref('val__all_violations') }}
where excludes_from_silver
    and (
        (grain = 'charge_item' and source_charge_item_id is null and row_ordinal is null)
        or (grain = 'code' and code_ordinal is null)
        or (grain = 'drug' and source_charge_item_id is null and row_ordinal is null)
        or (grain = 'standard_charge' and source_standard_charge_id is null and row_ordinal is null)
        or (
            grain = 'payer_rate'
            and (
                (source_standard_charge_id is null or payer_ordinal is null)
                and (row_ordinal is null or source_rate_ordinal is null)
            )
        )
        or (grain = 'modifier' and modifier_code_id is null and row_ordinal is null)
        or (grain = 'modifier_payer' and (modifier_code_id is null or modifier_payer_ordinal is null))
        or (grain = 'npi' and npi_ordinal is null)
        or (grain = 'provision' and provision_ordinal is null)
        or grain in ('file', 'header', 'structural')
    )
