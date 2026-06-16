{{ config(materialized='ephemeral') }}

with base_rates as (
    select
        pr.silver_payer_rate_id,
        pr.clean_payer_name,
        snapshots.canonical_state
    from {{ hpt_scoped_ref('slv_base__payer_rates') }} pr
    left join {{ hpt_scoped_ref('slv_base__hospital_snapshots') }} snapshots
        on pr.snapshot_id = snapshots.snapshot_id
),

candidate_matches as (
    select
        base_rates.silver_payer_rate_id,
        aliases.payer_alias_id,
        aliases.canonical_payer_id,
        aliases.review_status as payer_review_status,
        aliases.validation_status,
        aliases.match_scope,
        aliases.canonical_state,
        row_number() over (
            partition by base_rates.silver_payer_rate_id
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
    from base_rates
    inner join {{ ref('payer_aliases') }} aliases
        on base_rates.clean_payer_name = aliases.clean_payer_name
        and aliases.active = true
        and aliases.review_status = 'accepted'
        and (
            aliases.match_scope = 'global'
            or (
                aliases.match_scope = 'state'
                and aliases.canonical_state = base_rates.canonical_state
            )
        )
)

select
    silver_payer_rate_id,
    payer_alias_id,
    canonical_payer_id,
    payer_review_status,
    validation_status,
    match_scope,
    canonical_state
from candidate_matches
where match_rank = 1
