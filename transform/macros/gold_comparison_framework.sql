{#-
    Gold comparability framework.

    These macros encode the cross-hospital comparison classification once so that
    every consumer derives identical comparison_tier values and blocker reasons.
    They are SQL fragments that reference a fixed set of assembled column names
    (the fact + bridge surface), so call them in a select whose in-scope columns
    include exactly those names:

        is_current_snapshot, code_cross_hospital_comparable, code_is_specific,
        match_code, clean_setting, clean_billing_class, amount_unit, amount_role,
        amount_comparability_tier, has_pro_tech_split_modifier, is_drug_observation,
        drug_unit_status, observation_scope, canonical_payer_id, market_segment

    Used today by gld__service_price_comparison_current (plan §7.1) and intended for
    gld__snapshot_coverage_scorecard (plan §8.1). The one blocker that depends on a
    cross-hospital window — below_min_hospital_denominator — is NOT emitted here; it
    is computed by the consumer after the peer-count window is known.
-#}

{#- Comparison tiers. tier_3_canonical_service and
    tier_4_payer_plan_aligned are reserved (no service master / canonical plan in
    v1) and are never produced. -#}
{% macro hpt_comparison_tier() -%}
    case
        when coalesce(code_cross_hospital_comparable, false) = false
            then 'tier_0_trace_only'
        when coalesce(code_is_specific, false) = true
            and match_code is not null
            and clean_setting is not null
            and clean_billing_class is not null
            then 'tier_2_context_aligned'
        else 'tier_1_code_backed'
    end
{%- endmacro %}


{#- Typed boolean blocker flags. Every exclusion from a stricter use
    case is one of these stable codes; they are columns, never hidden WHERE
    clauses. Emitted as a comma-separated list of `<expr> as <blocker_code>`
    so the macro slots directly into a select list. -#}
{% macro hpt_comparison_blocker_flags() -%}
    coalesce(is_current_snapshot, false) = false
        as not_current_snapshot,
    coalesce(code_cross_hospital_comparable, false) = false
        as code_not_cross_hospital_comparable,
    (
        coalesce(code_cross_hospital_comparable, false) = true
        and coalesce(code_is_specific, false) = false
    ) as code_not_specific,
    match_code is null
        as missing_match_code,
    (
        amount_unit <> 'usd'
        or amount_role in ('allowed_amount_stat', 'estimated')
    ) as non_rankable_amount,
    coalesce(amount_comparability_tier = 'derived_dollar', false)
        as derived_dollar,
    coalesce(has_pro_tech_split_modifier, false)
        as modifier_context_required,
    coalesce(
        coalesce(is_drug_observation, false)
        and drug_unit_status = 'missing_unit',
        false
    ) as drug_unit_context_missing,
    (
        observation_scope = 'payer_rate'
        and (canonical_payer_id is null or canonical_payer_id = '<unmatched>')
    ) as payer_unmatched,
    coalesce(market_segment = 'unknown', false)
        as market_segment_unknown
{%- endmacro %}


{#- The stable blocker-code vocabulary, in the order the flags are emitted above
    plus the window-derived below_min_hospital_denominator. Consumers use this to
    build the blocker_reasons array and to lock the accepted set in tests. -#}
{% macro hpt_comparison_blocker_codes() -%}
    {{ return([
        'not_current_snapshot',
        'code_not_cross_hospital_comparable',
        'code_not_specific',
        'missing_match_code',
        'non_rankable_amount',
        'derived_dollar',
        'modifier_context_required',
        'drug_unit_context_missing',
        'payer_unmatched',
        'market_segment_unknown',
        'below_min_hospital_denominator'
    ]) }}
{%- endmacro %}
