with base_rates as (
    select
        pr.silver_payer_rate_id,
        pr.clean_payer_name,
        pr.clean_plan_name,
        snapshots.canonical_state
    from {{ ref('slv_base__payer_rates') }} pr
    left join {{ ref('slv_base__hospital_snapshots') }} snapshots
        on pr.snapshot_id = snapshots.snapshot_id
),

candidate_matches as (
    select
        base_rates.silver_payer_rate_id,
        overrides.payer_context_rule_id,
        overrides.canonical_payer_id,
        overrides.review_status as payer_review_status,
        overrides.validation_status,
        overrides.match_scope,
        overrides.canonical_state,
        row_number() over (
            partition by base_rates.silver_payer_rate_id
            order by
                case
                    when overrides.match_scope = 'state' then 0
                    else 1
                end,
                case overrides.match_type
                    when 'exact_clean' then 0
                    when 'token_contains' then 1
                    when 'plan_contains' then 2
                    when 'regex' then 3
                    else 99
                end,
                length(overrides.plan_pattern) desc,
                overrides.payer_context_rule_id
        ) as match_rank
    from base_rates
    inner join {{ ref('payer_context_overrides') }} overrides
        on base_rates.clean_payer_name = overrides.source_clean_payer_name
        and base_rates.clean_plan_name is not null
        and overrides.active = true
        and overrides.review_status = 'accepted'
        and (
            (
                overrides.match_type = 'exact_clean'
                and base_rates.clean_plan_name = overrides.plan_pattern
            )
            or (
                overrides.match_type = 'plan_contains'
                and contains(base_rates.clean_plan_name, overrides.plan_pattern)
            )
            or (
                overrides.match_type = 'token_contains'
                and regexp_matches(
                    base_rates.clean_plan_name,
                    '(^|[^a-z0-9])' || overrides.plan_pattern || '([^a-z0-9]|$)'
                )
            )
            or (
                overrides.match_type = 'regex'
                and regexp_matches(base_rates.clean_plan_name, overrides.plan_pattern)
            )
        )
        and (
            overrides.match_scope = 'global'
            or (
                overrides.match_scope = 'state'
                and overrides.canonical_state = base_rates.canonical_state
            )
        )
)

select
    silver_payer_rate_id,
    payer_context_rule_id,
    canonical_payer_id,
    payer_review_status,
    validation_status,
    match_scope,
    canonical_state
from candidate_matches
where match_rank = 1
