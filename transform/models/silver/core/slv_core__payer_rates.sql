with joined as (
    select
        pr.*,
        standard_charges.clean_setting,
        standard_charges.clean_billing_class,
        coalesce(rate_modifiers.modifier_signature, md5('<no_modifiers>')) as modifier_signature,
        coalesce(rate_modifiers.modifier_count, 0) as modifier_count,
        alias_matches.canonical_payer_id,
        canonical_payers.canonical_payer_name,
        canonical_payers.payer_parent_id,
        canonical_payers.payer_parent_name,
        canonical_payers.payer_type,
        coalesce(
            context_matches.market_segment,
            {{ hpt_clean_text('canonical_payers.default_market_segment') }},
            'unknown'
        ) as market_segment,
        context_matches.program_type,
        context_matches.product_or_network_name,
        context_matches.subsidiary_or_brand,
        coalesce(
            context_matches.benefit_line,
            {{ hpt_clean_text('canonical_payers.default_benefit_line') }},
            'unknown'
        ) as benefit_line,
        context_matches.funding_arrangement,
        context_matches.context_state,
        -- plan_type: prefer the payer-context rule, fall back to the deterministic
        -- structural derivation (ppo/hmo/pos/epo/pffs/hdhp word-boundary tokens).
        -- Enrichment only; never gates inclusion and never feeds market_segment.
        coalesce(
            context_matches.plan_type,
            {{ hpt_derive_plan_type('pr.clean_plan_name') }}
        ) as plan_type,
        -- Provenance of plan_type: a curated rule, the token derivation, or neither.
        case
            when context_matches.plan_type is not null then 'payer_context_rule'
            when {{ hpt_derive_plan_type('pr.clean_plan_name') }} is not null then 'derived_plan_type'
            else 'none'
        end as plan_type_basis,
        case
            when alias_matches.canonical_payer_id is not null then 'payer_alias'
            else 'unmatched'
        end as payer_match_basis,
        case
            when context_matches.payer_context_rule_id is not null then 'payer_context_rule'
            else 'no_context_rule'
        end as payer_context_match_basis,
        alias_matches.payer_alias_id,
        context_matches.payer_context_rule_id,
        context_matches.payer_context_review_status,
        context_matches.payer_context_confidence
    from {{ hpt_scoped_ref('slv_base__payer_rates') }} pr
    left join {{ hpt_scoped_ref('slv_base__standard_charges') }} standard_charges
        on pr.silver_standard_charge_id = standard_charges.silver_standard_charge_id
    left join {{ ref('slv_core__rate_modifier_signature') }} rate_modifiers
        on pr.silver_payer_rate_id = rate_modifiers.silver_payer_rate_id
    left join {{ ref('slv_core__payer_alias_matches') }} alias_matches
        on pr.silver_payer_rate_id = alias_matches.silver_payer_rate_id
    left join {{ ref('slv_core__payer_context_matches') }} context_matches
        on pr.silver_payer_rate_id = context_matches.silver_payer_rate_id
    left join {{ ref('canonical_payers') }} canonical_payers
        on alias_matches.canonical_payer_id = canonical_payers.canonical_payer_id
        and canonical_payers.active = true
),

methodology_enriched as (
    select
        *,
        coalesce({{ hpt_canonical_methodology('clean_methodology') }}, 'unmapped') as methodology,
        case
            when {{ hpt_canonical_methodology('clean_methodology') }} is null then 'unmapped'
            when {{ hpt_canonical_methodology('clean_methodology') }} = {{ hpt_clean_text('clean_methodology') }} then 'cms_value'
            else 'mapped'
        end as methodology_basis
    from joined
),

count_enriched as (
    select
        *,
        raw_count as count_raw,
        {{ hpt_count_min('raw_count') }} as count_min,
        {{ hpt_count_max('raw_count') }} as count_max
    from methodology_enriched
),

amount_flags as (
    select
        *,
        negotiated_dollar is not null as has_usable_dollar,
        negotiated_percentage is not null as has_usable_percentage,
        {{ hpt_clean_display_text('negotiated_algorithm') }} is not null as has_usable_algorithm,
        estimated_amount is not null as has_usable_estimated
    from count_enriched
),

amount_kind_enriched as (
    select
        *,
        case
            when has_usable_dollar then 'dollar'
            when has_usable_percentage then 'percentage'
            when has_usable_algorithm then 'algorithm'
            when has_usable_estimated then 'estimated'
            else 'none'
        end as amount_kind
    from amount_flags
),

amount_tiered as (
    select
        *,
        case
            when amount_kind = 'dollar'
                and methodology in ('fee schedule', 'case rate', 'per diem')
                then 'comparable_dollar'
            when amount_kind = 'dollar' then 'derived_dollar'
            when amount_kind = 'percentage' then 'percentage'
            when amount_kind = 'algorithm' then 'algorithm'
            else 'none'
        end as amount_comparability_tier
    from amount_kind_enriched
)

select
    * exclude (
        has_usable_dollar,
        has_usable_percentage,
        has_usable_algorithm,
        has_usable_estimated
    ),
    amount_comparability_tier = 'comparable_dollar' as is_price_comparable
from amount_tiered
