with base_drugs as (
    select *
    from {{ hpt_scoped_ref('slv_base__drug_information') }}
),

drug_unit_aliases as (
    select *
    from {{ ref('drug_unit_aliases') }}
),

ndc_items as (
    select distinct silver_charge_item_id
    from {{ hpt_scoped_ref('slv_base__charge_item_codes') }}
    where canonical_code_system = 'ndc'
)

select
    base_drugs.*,
    drug_unit_aliases.canonical_unit as canonical_drug_unit_type,
    drug_unit_aliases.unit_group as drug_unit_group,
    case
        when base_drugs.clean_drug_unit_type is null then 'missing_unit'
        when drug_unit_aliases.clean_unit_code is not null then 'canonical'
        else 'unknown_unit'
    end as drug_unit_status,
    ndc_items.silver_charge_item_id is not null as item_has_ndc_code,
    (
        ndc_items.silver_charge_item_id is not null
        and base_drugs.clean_drug_unit_type is null
    ) as ndc_item_missing_drug_unit
from base_drugs
left join drug_unit_aliases
    on base_drugs.clean_drug_unit_type = drug_unit_aliases.clean_unit_code
left join ndc_items
    on base_drugs.silver_charge_item_id = ndc_items.silver_charge_item_id
