with cases as (
    select *
    from (
        values
            ('bare_humana_unknown', 'humana', cast(null as varchar), 'humana-unknown'),
            ('humana_military_east_plan', 'humana', 'humana military east', 'humana-military-east'),
            ('humana_military_east_adult_plan', 'humana', 'humana military east adult', 'humana-military-east'),
            ('humana_military_east_behavioral_plan', 'humana', 'humana military east behavioral health', 'humana-military-east'),
            ('humana_military_alias', 'humana military', cast(null as varchar), 'humana-military-east'),
            ('humana_choicecare_ppo_alias', 'humana choicecare ppo', cast(null as varchar), 'humana-choicecare'),
            ('humana_choicecare_comm_plan_alias', 'humana choicecare', 'comm', 'humana-choicecare'),
            ('humana_ppo_choicecare_alias', 'humana ppo/choicecare', cast(null as varchar), 'humana-choicecare'),
            ('humanachoice_alias', 'humanachoice', cast(null as varchar), 'humana-choicecare'),
            ('humana_choicecare_plan', 'humana', 'humana choicecare ppo', 'humana-choicecare'),
            ('choicecare_beats_commercial_text', 'humana', 'choicecare all commercial plans', 'humana-choicecare'),
            ('humana_medicare_advantage_ppo_alias', 'humana medicare advantage ppo', cast(null as varchar), 'humana-medicare-advantage'),
            ('humana_medicare_advantage_hmo_pcp_plan', 'humana', 'medicare advantage hmo - pcp', 'humana-medicare-advantage'),
            ('humana_medicare_advantage_hmo_specialists_non_physician_plan', 'humana', 'medicare advantage hmo - specialists - non physician', 'humana-medicare-advantage'),
            ('humana_medicare_advantage_ppo_plan', 'humana', 'humana medicare advantage ppo', 'humana-medicare-advantage'),
            ('humana_medicare_transplant_adult_plan', 'humana', 'humana medicare transplant adult', 'humana-medicare-advantage'),
            ('humana_mcr_plan', 'humana', 'mcr', 'humana-medicare-advantage'),
            ('mcr_without_humana_context', 'mcr', cast(null as varchar), cast(null as varchar)),
            ('aetna_mcr_not_humana', 'aetna', 'mcr', 'aetna'),
            ('humana_dental_alias', 'humana dental', cast(null as varchar), 'humana-dental'),
            ('humana_dental_plan', 'humana', 'humana dental', 'humana-dental'),
            ('humana_commercial_plan', 'humana', 'commercial hmox - ppox & posx', 'humana-commercial'),
            ('humana_ntn_transplant_unknown', 'humana', 'humana ntn transplant adult', 'humana-unknown')
    ) as t(case_id, clean_payer_name, clean_plan_name, expected_canonical_payer_id)
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
        and aliases.match_scope = 'global'
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
        and overrides.match_scope = 'global'
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
