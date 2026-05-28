with cases as (
    select *
    from (
        values
            ('bare_aetna', 'aetna', cast(null as varchar), 'NA', 'aetna-unknown'),
            ('aetna_hmo_generic', 'aetna', 'hmo', 'TN', 'aetna-unknown'),
            ('aetna_medicare_named', 'aetna', 'aetna medicare behavioral health', 'TN', 'aetna-medicare-advantage'),
            ('aetna_medicare_advantage', 'aetna', 'medicare advantage esa', 'MI', 'aetna-medicare-advantage'),
            ('aetna_mcrppo', 'aetna', 'mcrppo', 'CA', 'aetna-medicare-advantage'),
            ('aetna_better_health', 'aetna', 'aetna better health adult', 'TN', 'aetna-better-health'),
            ('aetna_better_health_va', 'aetna', 'aetna better health of virginia', 'TN', 'aetna-better-health-virginia'),
            ('aetna_better_health_va_dsnp', 'aetna', 'aetna better health of virginia medicare', 'TN', 'aetna-better-health-virginia-dsnp'),
            ('aetna_whole_health', 'aetna', 'aetna whole health pediatric', 'TN', 'aetna-whole-health'),
            ('aetna_awh', 'aetna', 'awh', 'CA', 'aetna-whole-health'),
            ('aetna_vhan', 'aetna', 'aetna vhan behavioral health adult', 'TN', 'aetna-vhan'),
            ('aetna_tn_preferred_tn', 'aetna', 'aetna tn preferred adult', 'TN', 'aetna-tennessee-preferred'),
            ('aetna_tn_preferred_wrong_state', 'aetna', 'aetna tn preferred adult', 'CA', 'aetna-unknown'),
            ('aetna_commercial_named', 'aetna', 'aetna commercial behavioral health', 'TN', 'aetna-commercial'),
            ('aetna_all_commercial', 'aetna', 'all commercial plans', 'GA', 'aetna-commercial'),
            ('aetna_funding_advantage', 'aetna', 'commercial & aetna funding advantage plans', 'MI', 'aetna-funding-advantage'),
            ('aetna_workers_comp', 'aetna', 'workers'' compensation network', 'ID', 'aetna-workers-comp-auto'),
            ('aetna_auto_network', 'aetna', 'auto network', 'ID', 'aetna-workers-comp-auto'),
            ('multiplan_aetna_plan_not_aetna', 'multiplan, inc', 'aetna health plan ppo networks', 'WI', cast(null as varchar))
    ) as t(case_id, clean_payer_name, clean_plan_name, canonical_state, expected_canonical_payer_id)
),

alias_candidates as (
    select
        cases.case_id,
        aliases.payer_alias_id,
        aliases.canonical_payer_id,
        row_number() over (
            partition by cases.case_id
            order by
                case when aliases.match_scope = 'state' then 0 else 1 end,
                case aliases.validation_status
                    when 'source_verified' then 0
                    when 'manual_exact' then 1
                    when 'manual_alias' then 2
                    when 'inferred_from_pattern' then 3
                    else 5
                end,
                aliases.payer_alias_id
        ) as match_rank
    from cases
    inner join {{ ref('payer_aliases') }} aliases
        on cases.clean_payer_name = aliases.clean_payer_name
        and aliases.active = true
        and aliases.review_status = 'accepted'
        and aliases.match_type = 'exact_clean'
        and (
            aliases.match_scope = 'global'
            or (
                aliases.match_scope = 'state'
                and aliases.canonical_state = cases.canonical_state
            )
        )
),

alias_matches as (
    select
        case_id,
        payer_alias_id,
        canonical_payer_id
    from alias_candidates
    where match_rank = 1
),

context_candidates as (
    select
        cases.case_id,
        overrides.payer_context_rule_id,
        overrides.canonical_payer_id,
        row_number() over (
            partition by cases.case_id
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
    from cases
    inner join {{ ref('payer_context_overrides') }} overrides
        on cases.clean_payer_name = overrides.source_clean_payer_name
        and cases.clean_plan_name is not null
        and overrides.active = true
        and overrides.review_status = 'accepted'
        and (
            (
                overrides.match_type = 'exact_clean'
                and cases.clean_plan_name = overrides.plan_pattern
            )
            or (
                overrides.match_type = 'plan_contains'
                and contains(cases.clean_plan_name, overrides.plan_pattern)
            )
            or (
                overrides.match_type = 'token_contains'
                and regexp_matches(
                    cases.clean_plan_name,
                    '(^|[^a-z0-9])' || overrides.plan_pattern || '([^a-z0-9]|$)'
                )
            )
            or (
                overrides.match_type = 'regex'
                and regexp_matches(cases.clean_plan_name, overrides.plan_pattern)
            )
        )
        and (
            overrides.match_scope = 'global'
            or (
                overrides.match_scope = 'state'
                and overrides.canonical_state = cases.canonical_state
            )
        )
),

context_matches as (
    select
        case_id,
        payer_context_rule_id,
        canonical_payer_id
    from context_candidates
    where match_rank = 1
),

actual as (
    select
        cases.case_id,
        cases.clean_payer_name,
        cases.clean_plan_name,
        cases.canonical_state,
        cases.expected_canonical_payer_id,
        coalesce(context_matches.canonical_payer_id, alias_matches.canonical_payer_id)
            as actual_canonical_payer_id,
        alias_matches.payer_alias_id,
        context_matches.payer_context_rule_id
    from cases
    left join alias_matches
        on cases.case_id = alias_matches.case_id
    left join context_matches
        on cases.case_id = context_matches.case_id
)

select *
from actual
where actual_canonical_payer_id is distinct from expected_canonical_payer_id
