select
    {{ hpt_surrogate_key(['g.snapshot_id', 'g.provision_ordinal']) }} as silver_general_contract_provision_id,
    g.snapshot_id,
    s.hospital_id,
    s.source_format,
    g.provision_ordinal,
    g.raw_payer_name,
    g.clean_payer_name,
    g.raw_plan_name,
    g.clean_plan_name,
    g.raw_provisions,
    g.clean_provisions
from {{ hpt_scoped_ref('stg_bronze__general_contract_provisions') }} g
inner join {{ hpt_scoped_ref('slv_base__hospital_snapshots') }} s
    on g.snapshot_id = s.snapshot_id
where not exists (
    select 1
    from {{ hpt_scoped_ref('val__provision_rejections') }} r
    where r.snapshot_id = g.snapshot_id
        and r.provision_ordinal = g.provision_ordinal
)
