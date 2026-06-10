{{ config(materialized='ephemeral') }}

with base_rates as (
    select
        pr.silver_payer_rate_id,
        pr.clean_payer_name,
        pr.clean_plan_name,
        snapshots.canonical_state,
        alias_matches.canonical_payer_id
    from {{ hpt_scoped_ref('slv_base__payer_rates') }} pr
    inner join {{ ref('slv_core__payer_alias_matches') }} alias_matches
        on pr.silver_payer_rate_id = alias_matches.silver_payer_rate_id
    left join {{ hpt_scoped_ref('slv_base__hospital_snapshots') }} snapshots
        on pr.snapshot_id = snapshots.snapshot_id
),

match_inputs as (
    select distinct
        clean_payer_name,
        clean_plan_name,
        canonical_state,
        canonical_payer_id
    from base_rates
),

candidate_matches as (
    select
        match_inputs.clean_payer_name,
        match_inputs.clean_plan_name,
        match_inputs.canonical_state,
        match_inputs.canonical_payer_id,
        rules.payer_context_rule_id,
        rules.market_segment,
        rules.program_type,
        rules.product_or_network_name,
        rules.subsidiary_or_brand,
        rules.benefit_line,
        rules.funding_arrangement,
        rules.context_state,
        rules.plan_type,
        rules.context_confidence as payer_context_confidence,
        rules.review_status as payer_context_review_status,
        rules.validation_status,
        rules.match_type,
        rules.match_scope,
        rules.match_state,
        cast(rules.priority as integer) as priority,
        row_number() over (
            partition by
                match_inputs.clean_payer_name,
                match_inputs.clean_plan_name,
                match_inputs.canonical_state,
                match_inputs.canonical_payer_id
            order by
                cast(rules.priority as integer),
                case
                    when rules.match_scope = 'state' then 0
                    else 1
                end,
                case rules.match_type
                    when 'exact_clean' then 0
                    when 'payer_name' then 1
                    when 'token_contains' then 2
                    when 'plan_contains' then 3
                    when 'regex' then 4
                    else 99
                end,
                length(rules.plan_pattern) desc,
                rules.payer_context_rule_id
        ) as match_rank
    from match_inputs
    inner join {{ ref('payer_context_rules') }} rules
        on match_inputs.canonical_payer_id = rules.source_canonical_payer_id
        and rules.active = true
        and rules.review_status = 'accepted'
        and (
            {{ hpt_clean_text('rules.source_clean_payer_name') }} is null
            or match_inputs.clean_payer_name = rules.source_clean_payer_name
        )
        and (
            (
                rules.match_type = 'payer_name'
                and match_inputs.clean_payer_name = rules.plan_pattern
            )
            or (
                rules.match_type = 'exact_clean'
                and match_inputs.clean_plan_name = rules.plan_pattern
            )
            or (
                rules.match_type = 'plan_contains'
                and contains(match_inputs.clean_plan_name, rules.plan_pattern)
            )
            or (
                rules.match_type = 'token_contains'
                and regexp_matches(
                    match_inputs.clean_plan_name,
                    '(^|[^a-z0-9])' || rules.plan_pattern || '([^a-z0-9]|$)'
                )
            )
            or (
                rules.match_type = 'regex'
                and regexp_matches(match_inputs.clean_plan_name, rules.plan_pattern)
            )
        )
        and (
            rules.match_scope = 'global'
            or (
                rules.match_scope = 'state'
                and rules.match_state = match_inputs.canonical_state
            )
        )
),

best_matches as (
    select *
    from candidate_matches
    where match_rank = 1
)

select
    base_rates.silver_payer_rate_id,
    best_matches.payer_context_rule_id,
    {{ hpt_clean_text('best_matches.market_segment') }} as market_segment,
    {{ hpt_clean_text('best_matches.program_type') }} as program_type,
    {{ hpt_clean_text('best_matches.product_or_network_name') }} as product_or_network_name,
    {{ hpt_clean_text('best_matches.subsidiary_or_brand') }} as subsidiary_or_brand,
    {{ hpt_clean_text('best_matches.benefit_line') }} as benefit_line,
    {{ hpt_clean_text('best_matches.funding_arrangement') }} as funding_arrangement,
    {{ hpt_clean_text('best_matches.context_state', lowercase=false) }} as context_state,
    {{ hpt_clean_text('best_matches.plan_type') }} as plan_type,
    best_matches.payer_context_confidence,
    best_matches.payer_context_review_status,
    best_matches.validation_status,
    best_matches.match_type,
    best_matches.match_scope,
    best_matches.match_state,
    best_matches.priority
from base_rates
inner join best_matches
    on base_rates.clean_payer_name = best_matches.clean_payer_name
    and (
        base_rates.clean_plan_name = best_matches.clean_plan_name
        or (
            base_rates.clean_plan_name is null
            and best_matches.clean_plan_name is null
        )
    )
    and (
        base_rates.canonical_state = best_matches.canonical_state
        or (
            base_rates.canonical_state is null
            and best_matches.canonical_state is null
        )
    )
    and base_rates.canonical_payer_id = best_matches.canonical_payer_id
