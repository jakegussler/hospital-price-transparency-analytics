-- gld_mart__service_price_summary
--
-- Aggregate variation/distribution model. Grain: one row per exact comparison
-- context = (service_code_key, clean_setting, clean_billing_class,
-- modifier_signature, amount_kind, comparison_methodology,
-- canonical_drug_unit_type) — equivalently one row per service_context_key.
--
-- Decision 0021: every distribution statistic (min/P10/median/P90/max/IQR/
-- spread/outliers) is computed over ONE representative amount per hospital
-- (gld_int__hospital_service_amounts), never over raw observations, and every
-- cohort contains exactly one negotiated methodology. Repeated contract rows
-- cannot add statistical weight, and per-diem daily rates never mix with
-- case-rate or fee-schedule dollars.
--
-- Denominator rule (0017 as amended by 0021): the 3-hospital publish floor
-- counts hospitals with a VALID representative amount (hospital_count).
-- reporting_hospital_count (any raw ranking row) and excluded_hospital_count
-- (reporting but unrepresentable — ambiguous contracts) are always published
-- beside it so the denominator definition is visible. Outliers are flagged
-- hospitals (robust 1.5×IQR fences over hospital amounts), never winsorized.
--
-- Cross-snapshot aggregate → full-refresh table (marts config).

with hospital_amounts as (
    select *
    from {{ ref('gld_int__hospital_service_amounts') }}
),

-- Total distinct hospitals with any valid representative (market_coverage_rate
-- denominator).
market_size as (
    select count(distinct hospital_id) as total_rankable_hospitals
    from hospital_amounts
    where hospital_amount is not null
),

group_stats as (
    select
        service_context_key,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        comparison_methodology,
        canonical_drug_unit_type,

        -- denominators and reconciliation counts
        sum(raw_observation_count) as observation_count,
        sum(source_contract_count) as contract_count,
        count(*) as reporting_hospital_count,
        count(hospital_amount) as hospital_count,
        count(*) - count(hospital_amount) as excluded_hospital_count,
        sum(coalesce(ambiguous_contract_count, 0)) as ambiguous_contract_count,

        -- distribution over ONE amount per hospital
        min(hospital_amount) as min_amount,
        quantile_cont(hospital_amount, 0.1) as p10_amount,
        quantile_cont(hospital_amount, 0.25) as p25_amount,
        median(hospital_amount) as median_amount,
        quantile_cont(hospital_amount, 0.75) as p75_amount,
        quantile_cont(hospital_amount, 0.9) as p90_amount,
        max(hospital_amount) as max_amount
    from hospital_amounts
    group by 1, 2, 3, 4, 5, 6, 7, 8
),

-- Distinct matched payers behind the context's contracts (negotiated only).
payer_counts as (
    select
        service_context_key,
        count(distinct case
            when canonical_payer_id is not null
                and canonical_payer_id <> '<unmatched>'
            then canonical_payer_id
        end) as payer_count
    from {{ ref('gld_int__service_contract_representatives') }}
    group by 1
),

-- Robust IQR outlier flag per group over HOSPITAL amounts, counted back.
outliers as (
    select
        h.service_context_key,
        sum((
            h.hospital_amount < g.p25_amount - 1.5 * (g.p75_amount - g.p25_amount)
            or h.hospital_amount > g.p75_amount + 1.5 * (g.p75_amount - g.p25_amount)
        )::int) as outlier_hospital_count
    from hospital_amounts as h
    join group_stats as g
        on h.service_context_key = g.service_context_key
    where h.hospital_amount is not null
    group by 1
)

select
    g.service_context_key,
    g.service_code_key,
    g.clean_setting,
    g.clean_billing_class,
    g.modifier_signature,
    g.amount_kind,
    g.comparison_methodology,
    g.canonical_drug_unit_type,

    -- denominators (always published; each count supports a different claim)
    g.observation_count,
    g.contract_count,
    g.reporting_hospital_count,
    g.hospital_count,
    g.excluded_hospital_count,
    g.ambiguous_contract_count,
    coalesce(pc.payer_count, 0) as payer_count,
    (g.hospital_count >= 3) as meets_hospital_threshold,
    g.hospital_count / nullif(m.total_rankable_hospitals, 0)::double
        as market_coverage_rate,

    -- distribution stats (suppressed below the 3-valid-hospital floor)
    case when g.hospital_count >= 3 then g.min_amount end as min_amount,
    case when g.hospital_count >= 3 then g.p10_amount end as p10_amount,
    case when g.hospital_count >= 3 then g.median_amount end as median_amount,
    case when g.hospital_count >= 3 then g.p90_amount end as p90_amount,
    case when g.hospital_count >= 3 then g.max_amount end as max_amount,
    case
        when g.hospital_count >= 3 then g.p75_amount - g.p25_amount
    end as iqr_amount,
    case
        when g.hospital_count >= 3 and g.p10_amount <> 0
        then g.p90_amount / g.p10_amount
    end as spread_ratio_p90_to_p10,
    case
        when g.hospital_count >= 3 then o.outlier_hospital_count
    end as outlier_hospital_count
from group_stats as g
cross join market_size as m
left join payer_counts as pc
    on g.service_context_key = pc.service_context_key
left join outliers as o
    on g.service_context_key = o.service_context_key
