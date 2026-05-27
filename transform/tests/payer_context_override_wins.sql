select
    core.silver_payer_rate_id,
    core.clean_payer_name,
    core.clean_plan_name,
    core.canonical_payer_id,
    core.payer_match_basis
from {{ ref('slv_core__payer_rates') }} core
left join {{ ref('slv_base__hospital_snapshots') }} snapshots
    on core.snapshot_id = snapshots.snapshot_id
inner join {{ ref('payer_context_overrides') }} overrides
    on core.clean_payer_name = overrides.source_clean_payer_name
    and overrides.active = true
    and overrides.review_status = 'accepted'
    and (
        (
            overrides.match_type = 'exact_clean'
            and core.clean_plan_name = overrides.plan_pattern
        )
        or (
            overrides.match_type = 'plan_contains'
            and contains(core.clean_plan_name, overrides.plan_pattern)
        )
        or (
            overrides.match_type = 'token_contains'
            and regexp_matches(
                core.clean_plan_name,
                '(^|[^a-z0-9])' || overrides.plan_pattern || '([^a-z0-9]|$)'
            )
        )
        or (
            overrides.match_type = 'regex'
            and regexp_matches(core.clean_plan_name, overrides.plan_pattern)
        )
    )
    and (
        overrides.match_scope = 'global'
        or (
            overrides.match_scope = 'state'
            and overrides.canonical_state = snapshots.canonical_state
        )
    )
where core.payer_match_basis <> 'payer_context_override'
    or core.canonical_payer_id <> overrides.canonical_payer_id
