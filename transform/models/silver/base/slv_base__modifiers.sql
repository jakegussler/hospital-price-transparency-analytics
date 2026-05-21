select
    {{ hpt_surrogate_key([
        'm.modifier_code_id',
        'mpi.raw_payer_name',
        'mpi.raw_plan_name',
        'mpi.raw_description'
    ]) }} as silver_modifier_id,
    m.modifier_code_id as source_modifier_code_id,
    m.snapshot_id,
    hs.hospital_id,
    hs.source_format,
    m.raw_modifier_code,
    m.clean_modifier_code,
    m.raw_description,
    m.clean_description,
    m.raw_setting,
    m.clean_setting,
    mpi.raw_payer_name,
    mpi.clean_payer_name,
    mpi.raw_plan_name,
    mpi.clean_plan_name,
    mpi.raw_description as raw_modifier_payer_description,
    mpi.clean_description as clean_modifier_payer_description
from {{ ref('stg_bronze__modifiers') }} m
inner join {{ ref('slv_base__hospital_snapshots') }} hs
    on m.snapshot_id = hs.snapshot_id
left join {{ ref('stg_bronze__modifier_payer_info') }} mpi
    on m.snapshot_id = mpi.snapshot_id
    and m.modifier_code_id = mpi.modifier_code_id
