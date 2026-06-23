{{ config(tags=['silver_core']) }}

with cases as (
    select *
    from (
        values
            (
                'bare_aetna',
                'aetna',
                cast(null as varchar),
                'NA',
                'aetna',
                'unknown',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'aetna_medicare_advantage',
                'aetna',
                'medicare advantage esa',
                'MI',
                'aetna',
                'medicare_advantage',
                'medicare_advantage',
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'aetna_better_health_va_dsnp',
                'aetna',
                'aetna better health of virginia medicare',
                'TN',
                'aetna',
                'medicare_advantage',
                'dsnp',
                cast(null as varchar),
                'aetna_better_health',
                'medical',
                'VA'
            ),
            (
                'aetna_whole_health',
                'aetna',
                'aetna whole health pediatric',
                'TN',
                'aetna',
                'commercial',
                cast(null as varchar),
                'aetna_whole_health',
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'aetna_tn_preferred_wrong_state',
                'aetna',
                'aetna tn preferred adult',
                'CA',
                'aetna',
                'unknown',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'uhc_tenncare',
                'uhc',
                'uhc community plan/tenncare adult',
                'TN',
                'unitedhealthcare',
                'medicaid_managed_care',
                'tenncare',
                cast(null as varchar),
                'unitedhealthcare_community_plan',
                'medical',
                'TN'
            ),
            (
                'uhc_dsnp_beats_community_plan',
                'uhc',
                'uhc community plan/dsnp',
                'TN',
                'unitedhealthcare',
                'medicare_advantage',
                'dsnp',
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'united_dbp',
                'united',
                'united dbp',
                'TN',
                'unitedhealthcare',
                'commercial',
                cast(null as varchar),
                'dental_benefit_providers',
                cast(null as varchar),
                'dental',
                cast(null as varchar)
            ),
            (
                'united_healthcare_west_ca',
                'united healthcare west',
                'ucd hb uhc hmo referred',
                'CA',
                'unitedhealthcare',
                'commercial',
                cast(null as varchar),
                'unitedhealthcare_west',
                cast(null as varchar),
                'medical',
                'CA'
            ),
            (
                'umr_stays_distinct',
                'united medical resource(umr)',
                'ucd hb uhc non hmo',
                'CA',
                'umr',
                'commercial',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'surest_stays_distinct',
                'surest',
                'ucd hb uhc select & select plus',
                'CA',
                'surest',
                'commercial',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'united_behavioral_health_to_optum_context',
                'united behavioral health',
                cast(null as varchar),
                'CA',
                'optum',
                'commercial',
                cast(null as varchar),
                cast(null as varchar),
                'optum',
                'behavioral_health',
                cast(null as varchar)
            ),
            (
                'humana_choicecare_plan',
                'humana',
                'humana choicecare ppo',
                'NA',
                'humana',
                'commercial',
                cast(null as varchar),
                'humana_choicecare',
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'humana_mcr_plan',
                'humana',
                'mcr',
                'NA',
                'humana',
                'medicare_advantage',
                'medicare_advantage',
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'humana_dental_alias',
                'humana dental',
                cast(null as varchar),
                'NA',
                'humana',
                'commercial',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'dental',
                cast(null as varchar)
            ),
            (
                'blue_cross_ca_covered_ca',
                'blue cross',
                'ucd hb blue cross covered ca',
                'CA',
                'anthem_blue_cross_california',
                'exchange_marketplace',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                'CA'
            ),
            (
                'blue_shield_ca_mcrppo',
                'blue shield',
                'mcrppo',
                'CA',
                'blue_shield_california',
                'medicare_advantage',
                'medicare_advantage',
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                'CA'
            ),
            (
                'bcbst_bluecare_plus',
                'bcbst',
                'bluecare plus',
                'TN',
                'bcbs_tennessee',
                'medicare_advantage',
                'dsnp',
                'bluecare_plus',
                'bluecare_tennessee',
                'medical',
                'TN'
            ),
            (
                'bcbs_michigan_bcn',
                'blue cross blue shield of michigan',
                'blue care network',
                'MI',
                'bcbs_michigan',
                'commercial',
                cast(null as varchar),
                'blue_care_network',
                cast(null as varchar),
                'medical',
                'MI'
            ),
            (
                'wellcare_medicare_alias',
                'wellcare medicare',
                cast(null as varchar),
                'TN',
                'wellcare',
                'medicare_advantage',
                'medicare_advantage',
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'wellpoint_tenncare_plan',
                'wellpoint',
                'wellpoint community care tenncare adult',
                'TN',
                'wellpoint',
                'medicaid_managed_care',
                'tenncare',
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                'TN'
            ),
            (
                'generic_ppo_stays_unknown_context',
                'united healthcare',
                'ppo',
                'TN',
                'unitedhealthcare',
                'unknown',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            ),
            (
                'third_party_aetna_plan_not_aetna',
                'multiplan, inc',
                'aetna health plan ppo networks',
                'WI',
                cast(null as varchar),
                'unknown',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'unknown',
                cast(null as varchar)
            ),
            (
                'cigna_exact_ppo',
                'cigna',
                'ppo',
                'NA',
                'cigna',
                'commercial',
                cast(null as varchar),
                cast(null as varchar),
                cast(null as varchar),
                'medical',
                cast(null as varchar)
            )
    ) as t(
        case_id,
        clean_payer_name,
        clean_plan_name,
        canonical_state,
        expected_canonical_payer_id,
        expected_market_segment,
        expected_program_type,
        expected_product_or_network_name,
        expected_subsidiary_or_brand,
        expected_benefit_line,
        expected_context_state
    )
),

-- Expected plan_type and plan_type_basis per case, mirroring the rule-vs-derivation
-- precedence in slv_core__payer_rates: a rule that supplies plan_type wins
-- (payer_context_rule); otherwise the deterministic token derivation fills it
-- (derived_plan_type); otherwise null (none). Kept separate so the original
-- case tuples stay untouched.
plan_type_expectations as (
    select *
    from (
        values
            ('bare_aetna', cast(null as varchar), 'none'),
            ('aetna_medicare_advantage', cast(null as varchar), 'none'),
            ('aetna_better_health_va_dsnp', cast(null as varchar), 'none'),
            ('aetna_whole_health', cast(null as varchar), 'none'),
            ('aetna_tn_preferred_wrong_state', cast(null as varchar), 'none'),
            ('uhc_tenncare', cast(null as varchar), 'none'),
            ('uhc_dsnp_beats_community_plan', cast(null as varchar), 'none'),
            ('united_dbp', cast(null as varchar), 'none'),
            ('united_healthcare_west_ca', 'hmo', 'derived_plan_type'),
            ('umr_stays_distinct', 'hmo', 'derived_plan_type'),
            ('surest_stays_distinct', cast(null as varchar), 'none'),
            ('united_behavioral_health_to_optum_context', cast(null as varchar), 'none'),
            ('humana_choicecare_plan', 'ppo', 'derived_plan_type'),
            ('humana_mcr_plan', cast(null as varchar), 'none'),
            ('humana_dental_alias', cast(null as varchar), 'none'),
            ('blue_cross_ca_covered_ca', cast(null as varchar), 'none'),
            ('blue_shield_ca_mcrppo', cast(null as varchar), 'none'),
            ('bcbst_bluecare_plus', cast(null as varchar), 'none'),
            ('bcbs_michigan_bcn', cast(null as varchar), 'none'),
            ('wellcare_medicare_alias', cast(null as varchar), 'none'),
            ('wellpoint_tenncare_plan', cast(null as varchar), 'none'),
            ('generic_ppo_stays_unknown_context', 'ppo', 'derived_plan_type'),
            ('third_party_aetna_plan_not_aetna', 'ppo', 'derived_plan_type'),
            ('cigna_exact_ppo', 'ppo', 'payer_context_rule')
    ) as t(case_id, expected_plan_type, expected_plan_type_basis)
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
        rules.payer_context_rule_id,
        {{ hpt_clean_text('rules.market_segment') }} as market_segment,
        {{ hpt_clean_text('rules.program_type') }} as program_type,
        {{ hpt_clean_text('rules.product_or_network_name') }} as product_or_network_name,
        {{ hpt_clean_text('rules.subsidiary_or_brand') }} as subsidiary_or_brand,
        {{ hpt_clean_text('rules.benefit_line') }} as benefit_line,
        {{ hpt_clean_text('rules.context_state', lowercase=false) }} as context_state,
        {{ hpt_clean_text('rules.plan_type') }} as plan_type,
        row_number() over (
            partition by cases.case_id
            order by
                cast(rules.priority as integer),
                case when rules.match_scope = 'state' then 0 else 1 end,
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
    from cases
    inner join alias_matches
        on cases.case_id = alias_matches.case_id
    inner join {{ ref('payer_context_rules') }} rules
        on alias_matches.canonical_payer_id = rules.source_canonical_payer_id
        and rules.active = true
        and rules.review_status = 'accepted'
        and (
            {{ hpt_clean_text('rules.source_clean_payer_name') }} is null
            or cases.clean_payer_name = rules.source_clean_payer_name
        )
        and (
            (
                rules.match_type = 'payer_name'
                and cases.clean_payer_name = rules.plan_pattern
            )
            or (
                rules.match_type = 'exact_clean'
                and cases.clean_plan_name = rules.plan_pattern
            )
            or (
                rules.match_type = 'plan_contains'
                and contains(cases.clean_plan_name, rules.plan_pattern)
            )
            or (
                rules.match_type = 'token_contains'
                and regexp_matches(
                    cases.clean_plan_name,
                    '(^|[^a-z0-9])' || rules.plan_pattern || '([^a-z0-9]|$)'
                )
            )
            or (
                rules.match_type = 'regex'
                and regexp_matches(cases.clean_plan_name, rules.plan_pattern)
            )
        )
        and (
            rules.match_scope = 'global'
            or (
                rules.match_scope = 'state'
                and rules.match_state = cases.canonical_state
            )
        )
),

context_matches as (
    select
        case_id,
        payer_context_rule_id,
        market_segment,
        program_type,
        product_or_network_name,
        subsidiary_or_brand,
        benefit_line,
        context_state,
        plan_type
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
        alias_matches.canonical_payer_id as actual_canonical_payer_id,
        cases.expected_market_segment,
        coalesce(
            context_matches.market_segment,
            {{ hpt_clean_text('canonical_payers.default_market_segment') }},
            'unknown'
        ) as actual_market_segment,
        cases.expected_program_type,
        context_matches.program_type as actual_program_type,
        cases.expected_product_or_network_name,
        context_matches.product_or_network_name as actual_product_or_network_name,
        cases.expected_subsidiary_or_brand,
        context_matches.subsidiary_or_brand as actual_subsidiary_or_brand,
        cases.expected_benefit_line,
        coalesce(
            context_matches.benefit_line,
            {{ hpt_clean_text('canonical_payers.default_benefit_line') }},
            'unknown'
        ) as actual_benefit_line,
        cases.expected_context_state,
        context_matches.context_state as actual_context_state,
        plan_type_expectations.expected_plan_type,
        coalesce(
            context_matches.plan_type,
            {{ hpt_derive_plan_type('cases.clean_plan_name') }}
        ) as actual_plan_type,
        plan_type_expectations.expected_plan_type_basis,
        case
            when context_matches.plan_type is not null then 'payer_context_rule'
            when {{ hpt_derive_plan_type('cases.clean_plan_name') }} is not null
                then 'derived_plan_type'
            else 'none'
        end as actual_plan_type_basis,
        alias_matches.payer_alias_id,
        context_matches.payer_context_rule_id
    from cases
    left join alias_matches
        on cases.case_id = alias_matches.case_id
    left join context_matches
        on cases.case_id = context_matches.case_id
    left join plan_type_expectations
        on cases.case_id = plan_type_expectations.case_id
    left join {{ ref('canonical_payers') }} canonical_payers
        on alias_matches.canonical_payer_id = canonical_payers.canonical_payer_id
        and canonical_payers.active = true
)

select *
from actual
where actual_canonical_payer_id is distinct from expected_canonical_payer_id
    or actual_market_segment is distinct from expected_market_segment
    or actual_program_type is distinct from expected_program_type
    or actual_product_or_network_name is distinct from expected_product_or_network_name
    or actual_subsidiary_or_brand is distinct from expected_subsidiary_or_brand
    or actual_benefit_line is distinct from expected_benefit_line
    or actual_context_state is distinct from expected_context_state
    or actual_plan_type is distinct from expected_plan_type
    or actual_plan_type_basis is distinct from expected_plan_type_basis
