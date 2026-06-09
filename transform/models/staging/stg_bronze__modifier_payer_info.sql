with staged as (
    select
        snapshot_id,
        modifier_code_id,
        cast(
            {{ hpt_bronze_column_or_null(
                'modifier_payer_info',
                'modifier_payer_ordinal',
                'integer'
            ) }} as integer
        ) as source_modifier_payer_ordinal,
        payer_name as raw_payer_name,
        {{ hpt_normalize_text('payer_name') }} as clean_payer_name,
        plan_name as raw_plan_name,
        {{ hpt_normalize_text('plan_name') }} as clean_plan_name,
        description as raw_description,
        {{ hpt_normalize_text('description') }} as clean_description
    from {{ source('bronze', 'modifier_payer_info') }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
)

select
    * exclude (source_modifier_payer_ordinal),
    coalesce(
        source_modifier_payer_ordinal,
        cast(
            row_number() over (
                partition by snapshot_id, modifier_code_id
                order by
                    coalesce(raw_payer_name, ''),
                    coalesce(raw_plan_name, ''),
                    coalesce(raw_description, '')
            ) - 1
            as integer
        )
    ) as modifier_payer_ordinal
from staged
