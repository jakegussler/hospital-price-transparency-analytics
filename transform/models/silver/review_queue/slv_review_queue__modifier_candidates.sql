with unreferenced_modifiers as (
    select
        charge_modifiers.match_modifier_code,
        charge_modifiers.raw_modifier_code,
        charge_modifiers.snapshot_id,
        charge_modifiers.hospital_id,
        charge_modifiers.source_format,
        charge_modifiers.source_modifier_code_id
    from {{ ref('slv_core__charge_modifiers') }} charge_modifiers
    where charge_modifiers.modifier_reference_status = 'no_reference'
        and charge_modifiers.snapshot_id in (
            {{ hpt_current_snapshot_ids_sql() }}
        )
),

source_definitions as (
    select
        snapshot_id,
        source_modifier_code_id,
        min(clean_description) as clean_description
    from {{ ref('slv_base__modifiers') }}
    group by snapshot_id, source_modifier_code_id
),

grouped as (
    select
        unreferenced_modifiers.match_modifier_code,
        count(*) as modifier_rows,
        count(distinct unreferenced_modifiers.hospital_id) as hospital_count,
        count(distinct unreferenced_modifiers.snapshot_id) as snapshot_count,
        count(distinct unreferenced_modifiers.source_format) as source_format_count,
        min(unreferenced_modifiers.raw_modifier_code) as example_raw_modifier_code,
        min(source_definitions.clean_description) filter (
            where source_definitions.clean_description is not null
        ) as example_source_definition
    from unreferenced_modifiers
    left join source_definitions
        on unreferenced_modifiers.snapshot_id = source_definitions.snapshot_id
        and unreferenced_modifiers.source_modifier_code_id = source_definitions.source_modifier_code_id
    group by unreferenced_modifiers.match_modifier_code
)

select
    {{ hpt_surrogate_key(['match_modifier_code']) }} as modifier_candidate_key,
    match_modifier_code,
    example_raw_modifier_code,
    example_source_definition,
    modifier_rows,
    hospital_count,
    snapshot_count,
    source_format_count,
    'needs_review' as review_queue_status
from grouped
order by
    modifier_rows desc,
    hospital_count desc,
    match_modifier_code
