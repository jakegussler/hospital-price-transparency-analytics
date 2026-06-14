-- Row-preserving Silver Core enrichment of Silver Base charge items: the
-- snapshot-independent content signatures and the derived within-hospital
-- service_item_id that lets the same item carry the same ID across snapshots.
-- Identity is algorithmic, not curated: specific clinical codes anchor the key
-- where they exist, the drift-tolerant description token signature separates
-- the genuinely different items that share a code, and categorical-only or
-- uncoded items fall back to lower-confidence keys. Signatures use match_code
-- so formatting drift (leading zeros, NDC layouts) cannot fracture identity.
with base_items as (
    select *
    from {{ hpt_scoped_ref('slv_base__charge_items') }}
),

-- One row per item: the sorted-set code signatures. string_agg skips the
-- nulls produced by the case filters, so an item with no qualifying codes
-- gets a null signature rather than a sentinel.
item_code_signatures as (
    select
        silver_charge_item_id,
        md5(
            string_agg(
                distinct case
                    when code_is_specific
                        then canonical_code_system || ':' || match_code
                end,
                '|' order by case
                    when code_is_specific
                        then canonical_code_system || ':' || match_code
                end
            )
        ) as code_signature_specific,
        md5(
            string_agg(
                distinct coalesce(canonical_code_system, clean_code_type, 'unknown')
                    || ':' || match_code,
                '|' order by coalesce(canonical_code_system, clean_code_type, 'unknown')
                    || ':' || match_code
            )
        ) as code_signature_all,
        string_agg(
            distinct case
                when canonical_code_system = 'ndc'
                    then match_code
            end,
            '|' order by case
                when canonical_code_system = 'ndc'
                    then match_code
            end
        ) as ndc_code_set
    from {{ hpt_scoped_ref('slv_core__charge_item_codes') }}
    where match_code is not null
    group by silver_charge_item_id
),

drug_unit_aliases as (
    select
        clean_unit_code,
        canonical_unit
    from {{ ref('drug_unit_aliases') }}
),

enriched_items as (
    select
        base_items.*,
        drug_unit_aliases.canonical_unit as canonical_drug_unit_type,
        md5({{ hpt_description_tokens('base_items.clean_description') }})
            as description_token_signature,
        item_code_signatures.code_signature_specific,
        item_code_signatures.code_signature_all,
        -- Drug identity is the canonical NDC set plus the unit the price is
        -- expressed in. drug_unit (the quantity) is deliberately excluded:
        -- profiling shows quantity-only distinctions are negligible (2 groups
        -- corpus-wide), and including it would mint a new ID whenever a
        -- hospital re-baselines its pricing quantity. Unknown units fall back
        -- to the clean value so they do not merge with missing units.
        case
            when item_code_signatures.ndc_code_set is not null
                or base_items.clean_drug_unit_type is not null
                or base_items.drug_unit is not null
                then {{ hpt_surrogate_key([
                    'item_code_signatures.ndc_code_set',
                    "coalesce(drug_unit_aliases.canonical_unit, base_items.clean_drug_unit_type)"
                ]) }}
        end as drug_signature
    from base_items
    left join item_code_signatures
        on base_items.silver_charge_item_id = item_code_signatures.silver_charge_item_id
    left join drug_unit_aliases
        on base_items.clean_drug_unit_type = drug_unit_aliases.clean_unit_code
)

select
    *,
    case
        when code_signature_specific is not null then 'specific_code'
        when code_signature_all is not null then 'categorical_code'
        else 'uncoded'
    end as service_item_identity_basis,
    case
        when code_signature_specific is not null then 'high'
        when code_signature_all is not null then 'medium'
        else 'low'
    end as service_item_identity_confidence,
    case
        when code_signature_specific is not null
            then {{ hpt_surrogate_key([
                'hospital_id',
                'code_signature_specific',
                'description_token_signature',
                'drug_signature'
            ]) }}
        when code_signature_all is not null
            then {{ hpt_surrogate_key([
                'hospital_id',
                'code_signature_all',
                'description_token_signature',
                'drug_signature'
            ]) }}
        else {{ hpt_surrogate_key([
            'hospital_id',
            'description_token_signature',
            'drug_signature'
        ]) }}
    end as service_item_id
from enriched_items
