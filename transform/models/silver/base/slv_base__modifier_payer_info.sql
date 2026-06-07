select
    {{ hpt_surrogate_key([
        'm.silver_modifier_id', 'mpi.modifier_payer_ordinal'
    ]) }} as silver_modifier_payer_info_id,
    m.silver_modifier_id,
    mpi.modifier_code_id as source_modifier_code_id,
    mpi.modifier_payer_ordinal,
    mpi.snapshot_id,
    m.hospital_id,
    m.source_format,
    mpi.raw_payer_name,
    mpi.clean_payer_name,
    mpi.raw_plan_name,
    mpi.clean_plan_name,
    mpi.raw_description,
    mpi.clean_description
from {{ ref('stg_bronze__modifier_payer_info') }} mpi
inner join {{ ref('slv_base__modifiers') }} m
    on mpi.snapshot_id = m.snapshot_id
    and mpi.modifier_code_id = m.source_modifier_code_id
where not exists (
    select 1
    from {{ ref('val__modifier_payer_rejections') }} r
    where r.snapshot_id = mpi.snapshot_id
        and r.modifier_code_id = mpi.modifier_code_id
        and r.modifier_payer_ordinal = mpi.modifier_payer_ordinal
)
