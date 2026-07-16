-- gld_int__hospital_service_amounts
--
-- Hospital-level representative amounts (decision 0021, level 2 of the market
-- statistic hierarchy). Grain: one row per (hospital_id, service_context_key)
-- over current snapshots — every hospital gets exactly ONE vote per exact
-- comparison context.
--
-- Negotiated dollars: the median of the hospital's VALID contract
-- representatives (gld_int__service_contract_representatives). A hospital whose
-- contracts are all ambiguous keeps its row with a NULL hospital_amount: it is a
-- reporting hospital, but it cannot be represented safely and is excluded from
-- market statistics (excluded, never silently averaged). Gross charges and
-- discounted cash have no contract concept: their hospital representative is
-- the median of the hospital's ranking rows in the context, unchanged from the
-- prior benchmarks logic.
--
-- Every market percentile, median, rank, and delta downstream (service summary,
-- comparison mart, hospital benchmarks, payer benchmarks) is computed over
-- hospital_amount from THIS model, so those marts reconcile by construction.
--
-- Cross-snapshot aggregate → full-refresh table (marts config).

-- Negotiated dollars: one vote per valid contract, then the hospital median.
with negotiated as (
    select
        hospital_id,
        service_context_key,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        comparison_methodology,
        canonical_drug_unit_type,
        sum(raw_observation_count) as raw_observation_count,
        count(*) as source_contract_count,
        count(*) filter (where not has_multiple_contract_amounts)
            as valid_contract_count,
        count(*) filter (where has_multiple_contract_amounts)
            as ambiguous_contract_count,
        count(distinct case
            when canonical_payer_id is not null
                and canonical_payer_id <> '<unmatched>'
            then canonical_payer_id
        end) as matched_payer_count,
        median(contract_representative_amount) as hospital_amount,
        count(contract_representative_amount) as hospital_amount_input_count
    from {{ ref('gld_int__service_contract_representatives') }}
    group by
        hospital_id, service_context_key, service_code_key, clean_setting,
        clean_billing_class, modifier_signature, amount_kind,
        comparison_methodology, canonical_drug_unit_type
),

-- Gross / cash: no contract concept; hospital median over ranking rows.
standard as (
    select
        hospital_id,
        service_context_key,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        comparison_methodology,
        canonical_drug_unit_type,
        count(*) as raw_observation_count,
        cast(null as bigint) as source_contract_count,
        cast(null as bigint) as valid_contract_count,
        cast(null as bigint) as ambiguous_contract_count,
        cast(0 as bigint) as matched_payer_count,
        median(amount_value) as hospital_amount,
        count(*) as hospital_amount_input_count
    from {{ ref('gld_int__service_comparison_spine') }}
    where comparison_tier = 'tier_2_context_aligned'
        and is_price_rankable = true
        and amount_kind in ('gross_charge', 'discounted_cash')
    group by
        hospital_id, service_context_key, service_code_key, clean_setting,
        clean_billing_class, modifier_signature, amount_kind,
        comparison_methodology, canonical_drug_unit_type
)

select * from negotiated
union all
select * from standard
