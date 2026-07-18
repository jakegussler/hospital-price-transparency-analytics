-- gld_mart__service_price_comparison_current
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
-- comparison_tier = tier_2_context_aligned AND is_price_rankable = true.
--
-- Decision 0021: market peer statistics are HOSPITAL-WEIGHTED and METHODOLOGY-
-- SEPARATED. The exact comparison context is service_context_key (code cohort +
-- setting + billing class + modifier signature + amount kind +
-- comparison_methodology + drug unit context). Market median/P10/P90, percentile
-- rank, and deltas come from one representative amount per hospital
-- (gld_int__hospital_service_amounts, itself built from deduplicated contract
-- representatives), so every ranked row of one hospital/context shares the
-- hospital's rank and deltas, and repeated contract rows add no weight. The
-- payer-specific cut is built the same way from contract representatives.
-- Rows whose contract/context has multiple distinct amounts carry the
-- multiple_amounts_per_contract_context blocker: visible here, excluded from
-- every representative statistic.
--
-- Cross-snapshot aggregate → full-refresh table. The code-expanded, classified
-- "expanded spine" (fact ⋈ bridge + the §6 comparison_tier / blocker columns) is
-- materialized once in gld_int__service_comparison_spine. This current mart and
-- its representative intermediates read the authoritative current-only view;
-- the coverage scorecard reads the retained-snapshot base. The classification
-- therefore stays identical without rebuilding the cross-hospital join.


with classified as (
    select *
    from {{ ref('gld_int__service_comparison_spine_current') }}
),

-- The un-expanded fact, kept only for item_amounts below: the gross/cash/
-- negotiated charge-item aggregates must be computed at the observation grain,
-- not the code-expanded spine grain (the cohort fan-out would skew median()).
fact as (
    select f.*
    from {{ ref('gld_fct__rate_observations') }} as f
    inner join {{ ref('gld_dim__snapshot') }} as ds
        on f.snapshot_id = ds.snapshot_id
    where ds.is_current_snapshot = true
),

-- One representative amount per hospital per exact context (decision 0021).
hosp_reps as (
    select
        hospital_id,
        service_context_key,
        hospital_amount
    from {{ ref('gld_int__hospital_service_amounts') }}
    where hospital_amount is not null
),

-- Hospital-weighted market peer stats: one vote per hospital.
peer_stats as (
    select
        service_context_key,
        count(*) as peer_hospital_count,
        median(hospital_amount) as market_median_amount,
        quantile_cont(hospital_amount, 0.1) as market_p10_amount,
        quantile_cont(hospital_amount, 0.9) as market_p90_amount
    from hosp_reps
    group by 1
),

-- Hospital-weighted rank: every ranked row of one hospital/context shares it.
hosp_rank as (
    select
        hospital_id,
        service_context_key,
        hospital_amount,
        percent_rank() over (
            partition by service_context_key
            order by hospital_amount
        ) as amount_pct_rank
    from hosp_reps
),

-- Payer-specific cut (matched payers only), from valid contract representatives:
-- one payer-hospital representative per exact context, then hospital-weighted
-- payer market stats.
payer_hosp as (
    select
        canonical_payer_id,
        hospital_id,
        service_context_key,
        median(contract_representative_amount) as payer_hospital_amount
    from {{ ref('gld_int__service_contract_representatives') }}
    where canonical_payer_id is not null
        and canonical_payer_id <> '<unmatched>'
        and contract_representative_amount is not null
    group by 1, 2, 3
),

payer_stats as (
    select
        canonical_payer_id,
        service_context_key,
        count(*) as payer_peer_hospital_count,
        median(payer_hospital_amount) as payer_market_median_amount
    from payer_hosp
    group by 1, 2
),

payer_rank as (
    select
        canonical_payer_id,
        hospital_id,
        service_context_key,
        payer_hospital_amount,
        percent_rank() over (
            partition by canonical_payer_id, service_context_key
            order by payer_hospital_amount
        ) as payer_amount_pct_rank
    from payer_hosp
),

-- Contract representative for THIS row's contract/context (decision 0021
-- lineage + the contract-grain ambiguity blocker).
contract_reps as (
    select
        hospital_id,
        snapshot_id,
        service_context_key,
        source_contract_key,
        contract_representative_amount,
        distinct_amount_count,
        has_multiple_contract_amounts
    from {{ ref('gld_int__service_contract_representatives') }}
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
        hr.hospital_amount,
        hk.amount_pct_rank as raw_amount_pct_rank,
        ps.peer_hospital_count,
        ps.market_median_amount as raw_market_median_amount,
        ps.market_p10_amount as raw_market_p10_amount,
        ps.market_p90_amount as raw_market_p90_amount,
        cr.contract_representative_amount,
        cr.distinct_amount_count as contract_distinct_amount_count,
        ph.payer_hospital_amount,
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
        ) as below_min_hospital_denominator,
        coalesce(cr.has_multiple_contract_amounts, false)
            as multiple_amounts_per_contract_context
    from classified as c
    left join hosp_reps as hr
        on c.hospital_id = hr.hospital_id
        and c.service_context_key = hr.service_context_key
    left join hosp_rank as hk
        on c.hospital_id = hk.hospital_id
        and c.service_context_key = hk.service_context_key
    left join peer_stats as ps
        on c.service_context_key = ps.service_context_key
    left join contract_reps as cr
        on c.hospital_id = cr.hospital_id
        and c.snapshot_id = cr.snapshot_id
        and c.service_context_key = cr.service_context_key
        and c.source_contract_key = cr.source_contract_key
    left join payer_hosp as ph
        on c.canonical_payer_id = ph.canonical_payer_id
        and c.hospital_id = ph.hospital_id
        and c.service_context_key = ph.service_context_key
    left join payer_rank as pr
        on c.canonical_payer_id = pr.canonical_payer_id
        and c.hospital_id = pr.hospital_id
        and c.service_context_key = pr.service_context_key
    left join payer_stats as pps
        on c.canonical_payer_id = pps.canonical_payer_id
        and c.service_context_key = pps.service_context_key
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
    s.comparison_methodology,
    s.service_context_key,

    -- measurement
    s.amount_kind,
    s.amount_role,
    s.amount_unit,
    s.amount_value,
    s.is_price_rankable,
    s.is_price_ranking_row,
    s.methodology,
    s.amount_comparability_tier,

    -- contract identity + representatives (decision 0021)
    s.clean_payer_name,
    s.clean_plan_name,
    s.source_contract_key,
    s.contract_identity_precision,
    s.contract_representative_amount,
    s.contract_distinct_amount_count,
    s.hospital_amount,

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
    s.multiple_amounts_per_contract_context,
    list_filter(
        [
            {%- for code in hpt_comparison_blocker_codes() %}
            case when s.{{ code }} then '{{ code }}' end{{ "," if not loop.last }}
            {%- endfor %}
        ],
        x -> x is not null
    ) as blocker_reasons,

    -- market peer measures (hospital-weighted, decision 0021): published only
    -- when the 3-valid-hospital denominator clears
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
        then s.hospital_amount - s.raw_market_median_amount
    end as delta_from_market_median,
    case
        when s.peer_hospital_count >= 3 and s.raw_market_median_amount <> 0
        then (s.hospital_amount - s.raw_market_median_amount)
            / s.raw_market_median_amount
    end as pct_delta_from_market_median,

    -- payer-specific peer measures (matched payer only; hospital-weighted from
    -- contract representatives; same denominator rule)
    s.payer_hospital_amount,
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
        then s.payer_hospital_amount - s.raw_payer_market_median_amount
    end as payer_delta_from_market_median,
    case
        when s.payer_peer_hospital_count >= 3
            and s.raw_payer_market_median_amount <> 0
        then (s.payer_hospital_amount - s.raw_payer_market_median_amount)
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
