with cases as (
    select *
    from (
        values
            ('anthem_ca_bare', 'anthem', cast(null as varchar), 'CA', 'anthem-blue-cross-california-unknown'),
            ('anthem_ca_medi_cal', 'anthem', 'medi-cal', 'CA', 'anthem-blue-cross-california-medicaid'),
            ('anthem_ca_exchange', 'anthem', 'exchangeepo', 'CA', 'anthem-blue-cross-california-exchange'),
            ('anthem_ca_mcr', 'anthem', 'mcr', 'CA', 'anthem-blue-cross-california-medicare-advantage'),
            ('blue_cross_ca_commercial', 'blue cross', 'ucd hb blue cross ppo', 'CA', 'anthem-blue-cross-california-commercial'),
            ('blue_cross_ca_covered_ca', 'blue cross', 'ucd hb blue cross covered ca', 'CA', 'anthem-blue-cross-california-exchange'),
            ('blue_cross_ca_med_adv', 'blue cross senior', 'ucd hb blue cross med adv', 'CA', 'anthem-blue-cross-california-medicare-advantage'),
            ('blue_shield_ca_bare', 'blue shield', cast(null as varchar), 'CA', 'blue-shield-california-unknown'),
            ('blue_shield_ca_mcrppo', 'blue shield', 'mcrppo', 'CA', 'blue-shield-california-medicare-advantage'),
            ('blue_shield_ca_commercial', 'blue shield', 'ucd hb blue shield ifp', 'CA', 'blue-shield-california-commercial'),
            ('bcbst_bluecare', 'bcbst', 'bcbst-bluecare adult', 'TN', 'bluecare-tennessee'),
            ('bcbst_bluecare_plus', 'bcbst', 'bluecare plus', 'TN', 'bcbs-tennessee-bluecare-plus'),
            ('bcbst_blueadvantage', 'bcbst', 'blue advantage', 'TN', 'bcbs-tennessee-blueadvantage'),
            ('bluecare_dsnp', 'bluecare', 'dsnp', 'TN', 'bcbs-tennessee-bluecare-plus'),
            ('blue_cross_tn_anthem_va_medicare', 'blue cross', 'anthem medicare virginia', 'TN', 'anthem-blue-cross-blue-shield-virginia-medicare-advantage'),
            ('blue_cross_tn_healthkeepers_medicaid', 'blue cross', 'anthem hlthkeep mediciad', 'TN', 'anthem-healthkeepers-virginia-medicaid'),
            ('bcbs_ga_anthem_ppo', 'bcbs', 'anthem ppo', 'GA', 'bcbs-georgia'),
            ('blue_cross_ga_shbp_medicare', 'blue cross', 'state health benefit plan medicare managed care plan', 'GA', 'bcbs-georgia-medicare-advantage'),
            ('anthem_wi_commercial', 'anthem blue cross blue shield wisconsin', 'anthem blue access ppo', 'WI', 'anthem-bcbs-wisconsin-commercial'),
            ('anthem_wi_mediblue', 'anthem blue cross blue shield wisconsin', 'anthem mediblue plus hmo', 'WI', 'anthem-bcbs-wisconsin-medicare-advantage'),
            ('anthem_wi_medicaid', 'anthem blue cross blue shield wisconsin', 'anthem wisconsin medicaid plans', 'WI', 'anthem-bcbs-wisconsin-medicaid'),
            ('anthem_wi_fep', 'anthem blue cross blue shield wisconsin', 'anthem federal employee program', 'WI', 'bcbs-federal-employee-program'),
            ('bcbs_michigan_bcn', 'blue cross blue shield of michigan', 'blue care network', 'MI', 'blue-care-network-michigan'),
            ('bcbs_michigan_bcn_ma', 'blue cross blue shield of michigan', 'blue care network medicare advantage hmo/pos', 'MI', 'blue-care-network-michigan-medicare-advantage'),
            ('bcbs_michigan_fep', 'blue cross blue shield of michigan', 'blue cross blue shield of michigan federal employee program', 'MI', 'bcbs-federal-employee-program'),
            ('blue_cross_idaho_ma', 'blue cross of idaho', 'medicare advantage', 'ID', 'blue-cross-idaho-medicare-advantage'),
            ('regence_idaho_ma', 'regence blueshield of idaho', 'medicare advantage', 'ID', 'regence-blueshield-idaho-medicare-advantage'),
            ('wellpoint_tenncare', 'wellpoint', 'wellpoint community care tenncare adult', 'TN', 'wellpoint-tennessee-medicaid'),
            ('wellpoint_medicare', 'wellpoint', 'wellpoint medicare adult', 'TN', 'wellpoint-medicare-advantage'),
            ('third_party_blue_cross_plan_not_blue_payer', 'healthcomp', 'ucd hb blue cross ppo', 'CA', cast(null as varchar))
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
