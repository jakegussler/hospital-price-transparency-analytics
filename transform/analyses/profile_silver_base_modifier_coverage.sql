select
    source_format,
    modifier_definition_match_status,
    count(*) as modifier_rows,
    count(distinct silver_standard_charge_id) as standard_charges_with_modifiers,
    count(distinct silver_charge_item_id) as charge_items_with_modifiers,
    count(distinct snapshot_id) as snapshots
from {{ ref('slv_base__charge_modifiers') }}
group by source_format, modifier_definition_match_status
order by source_format, modifier_definition_match_status
