-- Atomic rate-observation fact. Grain: one row per reported amount cell =
-- one (source charge/rate row, amount_kind) pair within one snapshot.
--
-- This is the foundational Gold model and the reconciliation backbone. It does
-- NOT fan out on billing code: a standard charge contributes up to four
-- observation rows (gross/cash/min/max) and a payer rate up to seven
-- (dollar/percentage/algorithm/estimated/median/p10/p90). Code expansion lives
-- in gld_bridge__rate_observation_code, which keeps this fact additive and
-- double-count-proof
--
-- Most rows are true price observations, but the grain also retains amount
-- cells that are not independently rankable prices (min/max bounds, percentages,
-- algorithms, estimated and allowed-amount-stat values) so coverage and
-- reconciliation stay complete. is_price_rankable gates the ranking subset:
-- only gross_charge, discounted_cash, and comparable_dollar negotiated_dollar
-- are rankable.
--
-- Snapshot-grained incremental (snapshot_replace on snapshot_id) reading its
-- snapshot-grained inputs through hpt_scoped_ref so a scoped --snapshot-ids run
-- prunes Bronze partitions and bounds memory. Materialization/strategy are
-- inherited from the gold config block in dbt_project.yml.

-- One row per standard charge: the modifiers attach at standard-charge grain and
-- apply to every payer rate beneath the charge. Built with match_modifier_code
-- (= upper(clean_modifier_code)) so the signature is identical to the one
-- slv_core__payer_rates carries for payer rates.
with modifier_rollup as (
    select
        silver_standard_charge_id,
        {{ hpt_modifier_signature('match_modifier_code') }} as modifier_signature,
        count(distinct match_modifier_code) as modifier_count,
        bool_or(affects_pro_tech_split) as has_pro_tech_split_modifier
    from {{ hpt_scoped_ref('slv_core__charge_modifiers') }}
    where match_modifier_code is not null
    group by silver_standard_charge_id
),

-- One row per charge item: drug context, collapsed off the (item, csv-row)-grained
-- drug information so the left join below cannot fan out the fact. drug_unit_status
-- keeps the most informative value (canonical > unknown_unit > missing_unit).
drug_rollup as (
    select
        silver_charge_item_id,
        bool_or(item_has_ndc_code) as item_has_ndc_code,
        max(canonical_drug_unit_type) as canonical_drug_unit_type,
        case min(
            case drug_unit_status
                when 'canonical' then 1
                when 'unknown_unit' then 2
                else 3
            end
        )
            when 1 then 'canonical'
            when 2 then 'unknown_unit'
            else 'missing_unit'
        end as drug_unit_status
    from {{ hpt_scoped_ref('slv_core__drug_information') }}
    group by silver_charge_item_id
),

snapshot_currentness as (
    select
        snapshot_id,
        is_current_snapshot
    from {{ hpt_scoped_ref('slv_base__hospital_snapshots') }}
),

-- Shared context for every standard_charge-scope observation. Amount columns are
-- carried through and unpivoted below.
standard_charge_base as (
    select
        sc.snapshot_id,
        sc.hospital_id,
        cast('standard_charge' as varchar) as observation_scope,
        sc.silver_standard_charge_id,
        sc.silver_charge_item_id,
        cast(null as varchar) as silver_payer_rate_id,
        sc.source_format,
        cast(null as varchar) as methodology,
        cast(null as varchar) as amount_comparability_tier,
        cast(null as boolean) as is_price_comparable,
        cast(null as integer) as count_min,
        cast(null as integer) as count_max,
        sc.clean_setting,
        sc.clean_billing_class,
        coalesce(mods.modifier_signature, {{ hpt_no_modifier_signature() }}) as modifier_signature,
        coalesce(mods.modifier_count, 0) as modifier_count,
        coalesce(mods.has_pro_tech_split_modifier, false) as has_pro_tech_split_modifier,
        cast(null as varchar) as canonical_payer_id,
        cast(null as varchar) as market_segment,
        cast(null as varchar) as benefit_line,
        cast(null as varchar) as plan_type,
        cast(null as varchar) as plan_type_basis,
        coalesce(drugs.item_has_ndc_code, false)
            or drugs.canonical_drug_unit_type is not null as is_drug_observation,
        drugs.canonical_drug_unit_type,
        drugs.drug_unit_status,
        coalesce(snap.is_current_snapshot, false) as is_current_snapshot,
        -- amount sources
        sc.gross_charge,
        sc.discounted_cash,
        sc.minimum,
        sc.maximum
    from {{ hpt_scoped_ref('slv_base__standard_charges') }} sc
    left join modifier_rollup mods
        on sc.silver_standard_charge_id = mods.silver_standard_charge_id
    left join drug_rollup drugs
        on sc.silver_charge_item_id = drugs.silver_charge_item_id
    left join snapshot_currentness snap
        on sc.snapshot_id = snap.snapshot_id
),

-- Shared context for every payer_rate-scope observation. Payer identity/context
-- already live on slv_core__payer_rates; the modifier rollup is re-derived here
-- only for has_pro_tech_split_modifier (the signature/count match what the rate
-- already carries).
payer_rate_base as (
    select
        pr.snapshot_id,
        pr.hospital_id,
        cast('payer_rate' as varchar) as observation_scope,
        pr.silver_standard_charge_id,
        pr.silver_charge_item_id,
        pr.silver_payer_rate_id,
        pr.source_format,
        pr.methodology,
        pr.amount_comparability_tier,
        pr.is_price_comparable,
        pr.count_min,
        pr.count_max,
        pr.clean_setting,
        pr.clean_billing_class,
        pr.modifier_signature,
        pr.modifier_count,
        coalesce(mods.has_pro_tech_split_modifier, false) as has_pro_tech_split_modifier,
        coalesce(pr.canonical_payer_id, '<unmatched>') as canonical_payer_id,
        pr.market_segment,
        pr.benefit_line,
        pr.plan_type,
        pr.plan_type_basis,
        coalesce(drugs.item_has_ndc_code, false)
            or drugs.canonical_drug_unit_type is not null as is_drug_observation,
        drugs.canonical_drug_unit_type,
        drugs.drug_unit_status,
        coalesce(snap.is_current_snapshot, false) as is_current_snapshot,
        -- amount sources
        pr.negotiated_dollar,
        pr.negotiated_percentage,
        pr.negotiated_algorithm,
        pr.estimated_amount,
        pr.median_amount,
        pr.tenth_percentile,
        pr.ninetieth_percentile
    from {{ hpt_scoped_ref('slv_core__payer_rates') }} pr
    left join modifier_rollup mods
        on pr.silver_standard_charge_id = mods.silver_standard_charge_id
    left join drug_rollup drugs
        on pr.silver_charge_item_id = drugs.silver_charge_item_id
    left join snapshot_currentness snap
        on pr.snapshot_id = snap.snapshot_id
),

-- One CTE per amount_kind, each emitting a row only where its source cell is
-- non-null (no phantom observations). UNION ALL is the house-style unpivot.

-- standard_charge scope -------------------------------------------------------
obs_gross_charge as (
    select *,
        cast('gross_charge' as varchar) as amount_kind,
        cast('gross' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(gross_charge as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        true as is_price_rankable
    from standard_charge_base
    where gross_charge is not null
),

obs_discounted_cash as (
    select *,
        cast('discounted_cash' as varchar) as amount_kind,
        cast('cash' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(discounted_cash as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        true as is_price_rankable
    from standard_charge_base
    where discounted_cash is not null
),

obs_min_negotiated as (
    select *,
        cast('min_negotiated' as varchar) as amount_kind,
        cast('bound' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(minimum as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from standard_charge_base
    where minimum is not null
),

obs_max_negotiated as (
    select *,
        cast('max_negotiated' as varchar) as amount_kind,
        cast('bound' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(maximum as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from standard_charge_base
    where maximum is not null
),

-- payer_rate scope ------------------------------------------------------------
obs_negotiated_dollar as (
    select *,
        cast('negotiated_dollar' as varchar) as amount_kind,
        cast('negotiated' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(negotiated_dollar as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        -- rankable only for comparable_dollar; derived_dollar is visible but not ranked
        coalesce(is_price_comparable, false) as is_price_rankable
    from payer_rate_base
    where negotiated_dollar is not null
),

obs_negotiated_percentage as (
    select *,
        cast('negotiated_percentage' as varchar) as amount_kind,
        cast('negotiated' as varchar) as amount_role,
        cast('percent' as varchar) as amount_unit,
        cast(negotiated_percentage as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from payer_rate_base
    where negotiated_percentage is not null
),

obs_negotiated_algorithm as (
    select *,
        cast('negotiated_algorithm' as varchar) as amount_kind,
        cast('negotiated' as varchar) as amount_role,
        cast('text' as varchar) as amount_unit,
        cast(null as decimal(18, 4)) as amount_value,
        negotiated_algorithm as raw_algorithm_value,
        false as is_price_rankable
    from payer_rate_base
    where negotiated_algorithm is not null
),

obs_estimated_amount as (
    select *,
        cast('estimated_amount' as varchar) as amount_kind,
        cast('estimated' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(estimated_amount as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from payer_rate_base
    where estimated_amount is not null
),

obs_median_amount as (
    select *,
        cast('median_amount' as varchar) as amount_kind,
        cast('allowed_amount_stat' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(median_amount as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from payer_rate_base
    where median_amount is not null
),

obs_p10_amount as (
    select *,
        cast('p10_amount' as varchar) as amount_kind,
        cast('allowed_amount_stat' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(tenth_percentile as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from payer_rate_base
    where tenth_percentile is not null
),

obs_p90_amount as (
    select *,
        cast('p90_amount' as varchar) as amount_kind,
        cast('allowed_amount_stat' as varchar) as amount_role,
        cast('usd' as varchar) as amount_unit,
        cast(ninetieth_percentile as decimal(18, 4)) as amount_value,
        cast(null as varchar) as raw_algorithm_value,
        false as is_price_rankable
    from payer_rate_base
    where ninetieth_percentile is not null
),

standard_charge_observations as (
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_gross_charge
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_discounted_cash
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_min_negotiated
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_max_negotiated
),

payer_rate_observations as (
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_negotiated_dollar
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_negotiated_percentage
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_negotiated_algorithm
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_estimated_amount
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_median_amount
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_p10_amount
    union all
    select
        snapshot_id, hospital_id, observation_scope, silver_standard_charge_id,
        silver_charge_item_id, silver_payer_rate_id, source_format, amount_kind,
        amount_role, amount_unit, amount_value, raw_algorithm_value,
        is_price_rankable, methodology, amount_comparability_tier,
        is_price_comparable, count_min, count_max, clean_setting,
        clean_billing_class, modifier_signature, modifier_count,
        has_pro_tech_split_modifier, canonical_payer_id, market_segment,
        benefit_line, plan_type, plan_type_basis, is_drug_observation,
        canonical_drug_unit_type, drug_unit_status, is_current_snapshot
    from obs_p90_amount
),

all_observations as (
    select * from standard_charge_observations
    union all
    select * from payer_rate_observations
)

select
    {{ hpt_surrogate_key([
        'observation_scope',
        "coalesce(silver_payer_rate_id, silver_standard_charge_id)",
        'amount_kind'
    ]) }} as gold_rate_observation_id,
    snapshot_id,
    hospital_id,
    observation_scope,
    silver_standard_charge_id,
    silver_charge_item_id,
    silver_payer_rate_id,
    source_format,
    amount_kind,
    amount_role,
    amount_unit,
    amount_value,
    raw_algorithm_value,
    is_price_rankable,
    methodology,
    amount_comparability_tier,
    is_price_comparable,
    count_min,
    count_max,
    clean_setting,
    clean_billing_class,
    modifier_signature,
    modifier_count,
    modifier_count > 0 as has_modifier,
    has_pro_tech_split_modifier,
    canonical_payer_id,
    market_segment,
    benefit_line,
    plan_type,
    plan_type_basis,
    is_drug_observation,
    canonical_drug_unit_type,
    drug_unit_status,
    is_current_snapshot
from all_observations
