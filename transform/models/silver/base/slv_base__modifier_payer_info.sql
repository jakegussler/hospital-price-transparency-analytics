with json_modifier_payers as (
    select
        {{ hpt_surrogate_key(['m.silver_modifier_id', 'mpi.modifier_payer_ordinal']) }} as silver_modifier_payer_info_id,
        m.silver_modifier_id,
        mpi.modifier_code_id as source_modifier_code_id,
        cast(null as integer) as source_row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        mpi.modifier_payer_ordinal,
        mpi.snapshot_id,
        m.hospital_id,
        m.source_format,
        mpi.raw_payer_name,
        mpi.clean_payer_name,
        mpi.raw_plan_name,
        mpi.clean_plan_name,
        mpi.raw_description,
        mpi.clean_description,
        cast(null as varchar) as raw_methodology,
        cast(null as varchar) as clean_methodology,
        cast(null as decimal(18, 4)) as negotiated_dollar,
        cast(null as double) as negotiated_percentage,
        cast(null as varchar) as negotiated_algorithm,
        cast(null as decimal(18, 4)) as median_amount,
        cast(null as decimal(18, 4)) as tenth_percentile,
        cast(null as decimal(18, 4)) as ninetieth_percentile,
        cast(null as varchar) as raw_count,
        cast(null as varchar) as additional_generic_notes,
        cast(null as varchar) as additional_payer_notes
    from {{ ref('stg_bronze__modifier_payer_info') }} mpi
    inner join {{ ref('slv_base__modifiers') }} m
        on mpi.snapshot_id = m.snapshot_id
        and mpi.modifier_code_id = m.source_modifier_code_id
    where not exists (
        select 1
        from {{ ref('val__modifier_payer_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = mpi.snapshot_id
            and r.modifier_code_id = mpi.modifier_code_id
            and r.modifier_payer_ordinal = mpi.modifier_payer_ordinal
    )
),

csv_modifier_payers as (
    select
        {{ hpt_surrogate_key(['m.silver_modifier_id', 'r.source_rate_ordinal']) }} as silver_modifier_payer_info_id,
        m.silver_modifier_id,
        cast(null as varchar) as source_modifier_code_id,
        r.row_ordinal as source_row_ordinal,
        r.source_rate_ordinal,
        r.source_rate_ordinal as modifier_payer_ordinal,
        r.snapshot_id,
        m.hospital_id,
        m.source_format,
        r.raw_payer_name,
        r.clean_payer_name,
        r.raw_plan_name,
        r.clean_plan_name,
        cast(null as varchar) as raw_description,
        cast(null as varchar) as clean_description,
        r.raw_methodology,
        r.clean_methodology,
        r.negotiated_dollar,
        r.negotiated_percentage,
        r.negotiated_algorithm,
        r.median_amount,
        r.tenth_percentile,
        r.ninetieth_percentile,
        r.raw_count,
        r.additional_generic_notes,
        r.additional_payer_notes
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('slv_base__modifiers') }} m
        on r.snapshot_id = m.snapshot_id
        and r.row_ordinal = m.source_row_ordinal
        and m.definition_kind = 'csv_standalone_rule'
    where (
        r.clean_payer_name is not null
        or r.clean_plan_name is not null
        or r.clean_methodology is not null
        or r.negotiated_dollar is not null
        or r.negotiated_percentage is not null
        or {{ hpt_clean_display_text('r.negotiated_algorithm') }} is not null
        or r.median_amount is not null
        or r.tenth_percentile is not null
        or r.ninetieth_percentile is not null
        or {{ hpt_clean_display_text('r.raw_count') }} is not null
        or {{ hpt_clean_display_text('r.additional_generic_notes') }} is not null
        or {{ hpt_clean_display_text('r.additional_payer_notes') }} is not null
    )
    and not exists (
        select 1
        from {{ ref('val__modifier_payer_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
            and rej.source_rate_ordinal = r.source_rate_ordinal
    )
)

select * from json_modifier_payers
union all
select * from csv_modifier_payers
