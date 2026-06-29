-- gld__service_price_comparison_current
--
-- User question: "For this service (code cohort + context), which hospitals report
-- comparable current prices, how do they vary, and how much should I trust it?"
--
-- Grain: one row per (gold_rate_observation_id, service_code_key) over CURRENT
-- snapshots only. This is the code-expanded, blocker-annotated surface decision
-- 0017 calls the "expanded spine"; here it is fact ⋈ bridge ⋈ dims with the atomic
-- fact underneath guaranteeing no double count.
--
-- Inclusion: is_current_snapshot = true. ALL tiers are retained — every
-- non-qualifying row stays with its comparison_tier and blocker_reasons set, never
-- dropped (a blocker, never a hidden WHERE). The price-ranking subset is
-- comparison_tier = tier_2_context_aligned AND is_price_rankable = true; peer stats
-- are computed only over that subset and nulled below the 3-hospital denominator.
--
-- Two peer cuts are published: the MARKET-WIDE cut (partitioned by service_code_key
-- + setting + billing_class + modifier_signature + amount_kind) and the
-- PAYER-SPECIFIC cut (same, additionally by canonical_payer_id) for matched-payer
-- negotiated dollars. Guarded gross/cash and cash/negotiated ratios are carried per
-- charge-item context.
--
-- Cross-snapshot aggregate → full-refresh table. The code-expanded, classified
-- "expanded spine" (fact ⋈ bridge + the §6 comparison_tier / blocker columns) is
-- materialized once in gld_int__service_comparison_spine and read back here; this
-- mart references it five times (rankable, peer_stats, payer_rankable,
-- payer_peer_stats, scored), so persisting it as a table — rather than an inline
-- CTE DuckDB rebuilds per reference — is what keeps the cross-hospital build
-- inside memory. The classification comes from the gold_comparison_framework
-- macros (hpt_comparison_tier / hpt_comparison_blocker_flags) so this mart and the
-- coverage scorecard classify identically.


with classified as (
    select *
    from {{ ref('gld_int__service_comparison_spine') }}
),

-- The un-expanded fact, kept only for item_amounts below: the gross/cash/
-- negotiated charge-item aggregates must be computed at the observation grain,
-- not the code-expanded spine grain (the cohort fan-out would skew median()).
fact as (
    select *
    from {{ ref('gld_fct__rate_observations') }}
    where is_current_snapshot = true
),

-- Market price-ranking subset: tier_2 + dollar-rankable rows only.
rankable as (
    select
        gold_rate_observation_id,
        service_code_key,
        percent_rank() over (
            partition by
                service_code_key,
                clean_setting,
                clean_billing_class,
                modifier_signature,
                amount_kind
            order by amount_value
        ) as amount_pct_rank
    from classified
    where comparison_tier = 'tier_2_context_aligned'
        and is_price_rankable = true
),

peer_stats as (
    select
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        count(distinct hospital_id) as peer_hospital_count,
        median(amount_value) as market_median_amount,
        quantile_cont(amount_value, 0.1) as market_p10_amount,
        quantile_cont(amount_value, 0.9) as market_p90_amount
    from classified
    where comparison_tier = 'tier_2_context_aligned'
        and is_price_rankable = true
    group by 1, 2, 3, 4, 5
),

-- Payer-specific cut: same partition additionally by canonical_payer_id, limited
-- to matched-payer rankable rows (negotiated dollars with an identity).
payer_rankable as (
    select
        gold_rate_observation_id,
        service_code_key,
        percent_rank() over (
            partition by
                service_code_key,
                clean_setting,
                clean_billing_class,
                modifier_signature,
                amount_kind,
                canonical_payer_id
            order by amount_value
        ) as payer_amount_pct_rank
    from classified
    where comparison_tier = 'tier_2_context_aligned'
        and is_price_rankable = true
        and canonical_payer_id is not null
        and canonical_payer_id <> '<unmatched>'
),

payer_peer_stats as (
    select
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        canonical_payer_id,
        count(distinct hospital_id) as payer_peer_hospital_count,
        median(amount_value) as payer_market_median_amount
    from classified
    where comparison_tier = 'tier_2_context_aligned'
        and is_price_rankable = true
        and canonical_payer_id is not null
        and canonical_payer_id <> '<unmatched>'
    group by 1, 2, 3, 4, 5, 6
),

-- Charge-item-context amounts for the guarded gross/cash/negotiated ratios. One
-- row per (item, snapshot, setting, billing_class, modifier_signature).
item_amounts as (
    select
        silver_charge_item_id,
        snapshot_id,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        max(case when amount_kind = 'gross_charge' then amount_value end)
            as item_gross_amount,
        max(case when amount_kind = 'discounted_cash' then amount_value end)
            as item_cash_amount,
        median(case
            when amount_kind = 'negotiated_dollar' and is_price_rankable = true
            then amount_value
        end) as item_negotiated_amount
    from fact
    group by 1, 2, 3, 4, 5
),

scored as (
    select
        c.*,
        r.amount_pct_rank as raw_amount_pct_rank,
        ps.peer_hospital_count,
        ps.market_median_amount as raw_market_median_amount,
        ps.market_p10_amount as raw_market_p10_amount,
        ps.market_p90_amount as raw_market_p90_amount,
        pr.payer_amount_pct_rank as raw_payer_amount_pct_rank,
        pps.payer_peer_hospital_count,
        pps.payer_market_median_amount as raw_payer_market_median_amount,
        ia.item_gross_amount,
        ia.item_cash_amount,
        ia.item_negotiated_amount,
        (
            c.comparison_tier = 'tier_2_context_aligned'
            and c.is_price_rankable = true
        ) as is_price_ranking_row,
        (
            c.comparison_tier = 'tier_2_context_aligned'
            and c.is_price_rankable = true
            and coalesce(ps.peer_hospital_count, 0) < 3
        ) as below_min_hospital_denominator
    from classified as c
    left join rankable as r
        on c.gold_rate_observation_id = r.gold_rate_observation_id
        and c.service_code_key is not distinct from r.service_code_key
    left join peer_stats as ps
        on c.service_code_key = ps.service_code_key
        and c.clean_setting is not distinct from ps.clean_setting
        and c.clean_billing_class is not distinct from ps.clean_billing_class
        and c.modifier_signature is not distinct from ps.modifier_signature
        and c.amount_kind = ps.amount_kind
    left join payer_rankable as pr
        on c.gold_rate_observation_id = pr.gold_rate_observation_id
        and c.service_code_key is not distinct from pr.service_code_key
    left join payer_peer_stats as pps
        on c.service_code_key = pps.service_code_key
        and c.clean_setting is not distinct from pps.clean_setting
        and c.clean_billing_class is not distinct from pps.clean_billing_class
        and c.modifier_signature is not distinct from pps.modifier_signature
        and c.amount_kind = pps.amount_kind
        and c.canonical_payer_id = pps.canonical_payer_id
    left join item_amounts as ia
        on c.silver_charge_item_id = ia.silver_charge_item_id
        and c.snapshot_id = ia.snapshot_id
        and c.clean_setting is not distinct from ia.clean_setting
        and c.clean_billing_class is not distinct from ia.clean_billing_class
        and c.modifier_signature is not distinct from ia.modifier_signature
)

select
    s.gold_rate_observation_id,
    s.service_code_key,
    s.snapshot_id,
    s.hospital_id,
    s.observation_scope,
    s.silver_standard_charge_id,
    s.silver_charge_item_id,
    s.silver_payer_rate_id,

    -- comparison context
    s.canonical_code_system,
    s.match_code,
    s.code_is_specific,
    s.code_cross_hospital_comparable,
    s.clean_setting,
    s.clean_billing_class,
    s.modifier_signature,
    s.has_pro_tech_split_modifier,
    s.is_drug_observation,
    s.canonical_drug_unit_type,
    s.drug_unit_status,

    -- measurement
    s.amount_kind,
    s.amount_role,
    s.amount_unit,
    s.amount_value,
    s.is_price_rankable,
    s.is_price_ranking_row,
    s.methodology,
    s.amount_comparability_tier,

    -- payer / segment context
    s.canonical_payer_id,
    dp.canonical_payer_name,
    dp.payer_parent_name,
    dp.payer_type,
    s.market_segment,
    s.benefit_line,
    s.plan_type,

    -- comparability framework
    s.comparison_tier,
    s.not_current_snapshot,
    s.code_not_cross_hospital_comparable,
    s.code_not_specific,
    s.missing_match_code,
    s.non_rankable_amount,
    s.derived_dollar,
    s.modifier_context_required,
    s.drug_unit_context_missing,
    s.payer_unmatched,
    s.market_segment_unknown,
    s.below_min_hospital_denominator,
    list_filter(
        [
            {%- for code in hpt_comparison_blocker_codes() %}
            case when s.{{ code }} then '{{ code }}' end{{ "," if not loop.last }}
            {%- endfor %}
        ],
        x -> x is not null
    ) as blocker_reasons,

    -- market peer measures: published only when the 3-hospital denominator clears
    s.peer_hospital_count,
    case when s.peer_hospital_count >= 3 then s.raw_market_median_amount end
        as market_median_amount,
    case when s.peer_hospital_count >= 3 then s.raw_market_p10_amount end
        as market_p10_amount,
    case when s.peer_hospital_count >= 3 then s.raw_market_p90_amount end
        as market_p90_amount,
    case when s.peer_hospital_count >= 3 then s.raw_amount_pct_rank end
        as amount_pct_rank,
    case
        when s.peer_hospital_count >= 3
        then s.amount_value - s.raw_market_median_amount
    end as delta_from_market_median,
    case
        when s.peer_hospital_count >= 3 and s.raw_market_median_amount <> 0
        then (s.amount_value - s.raw_market_median_amount)
            / s.raw_market_median_amount
    end as pct_delta_from_market_median,

    -- payer-specific peer measures (matched payer only; same denominator rule)
    s.payer_peer_hospital_count,
    case
        when s.payer_peer_hospital_count >= 3
        then s.raw_payer_market_median_amount
    end as payer_market_median_amount,
    case
        when s.payer_peer_hospital_count >= 3
        then s.raw_payer_amount_pct_rank
    end as payer_amount_pct_rank,
    case
        when s.payer_peer_hospital_count >= 3
        then s.amount_value - s.raw_payer_market_median_amount
    end as payer_delta_from_market_median,
    case
        when s.payer_peer_hospital_count >= 3
            and s.raw_payer_market_median_amount <> 0
        then (s.amount_value - s.raw_payer_market_median_amount)
            / s.raw_payer_market_median_amount
    end as payer_pct_delta_from_market_median,

    -- guarded charge-item ratios (denominator-zero cases nulled)
    s.item_gross_amount / nullif(s.item_cash_amount, 0) as gross_to_cash_ratio,
    s.item_cash_amount / nullif(s.item_negotiated_amount, 0)
        as cash_to_negotiated_ratio,

    -- hospital dimension attributes
    dh.canonical_state,
    dh.canonical_state_name,
    dh.hospital_type,
    dh.health_system,

    -- snapshot freshness attributes
    s.is_current_snapshot,
    ds.published_last_updated_on,
    ds.snapshot_age_days,
    ds.freshness_bucket
from scored as s
left join {{ ref('gld_dim__hospital') }} as dh
    on s.hospital_id = dh.hospital_id
left join {{ ref('gld_dim__snapshot') }} as ds
    on s.snapshot_id = ds.snapshot_id
left join {{ ref('gld_dim__payer') }} as dp
    on s.canonical_payer_id = dp.canonical_payer_id
