select
    {{ hpt_surrogate_key(['m.snapshot_id', 'm.modifier_code_id']) }} as silver_modifier_id,
    m.modifier_code_id as source_modifier_code_id,
    m.snapshot_id,
    hs.hospital_id,
    hs.source_format,
    m.raw_modifier_code,
    m.clean_modifier_code,
    m.raw_description,
    m.clean_description,
    m.raw_setting,
    m.clean_setting
from {{ hpt_scoped_ref('stg_bronze__modifiers') }} m
inner join {{ hpt_scoped_ref('slv_base__hospital_snapshots') }} hs
    on m.snapshot_id = hs.snapshot_id
where not exists (
    select 1
    from {{ hpt_scoped_ref('val__modifier_rejections') }} r
    where r.source_format_family = 'json'
        and r.snapshot_id = m.snapshot_id
        and r.modifier_code_id = m.modifier_code_id
)
