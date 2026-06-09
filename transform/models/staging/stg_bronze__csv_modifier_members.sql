with source_rows as (
    select
        snapshot_id,
        row_ordinal,
        any_value(raw_modifiers) as raw_modifier_combination
    from {{ ref('stg_bronze__csv_charge_rows') }}
    group by snapshot_id, row_ordinal
)

select
    r.snapshot_id,
    r.row_ordinal,
    cast(u.member_ordinal as integer) - 1 as member_ordinal,
    u.raw_modifier_code,
    {{ hpt_trimmed_text('u.raw_modifier_code') }} as clean_modifier_code
from source_rows r
cross join unnest(string_split(r.raw_modifier_combination, '|'))
    with ordinality as u(raw_modifier_code, member_ordinal)
where {{ hpt_trimmed_text('u.raw_modifier_code') }} is not null
