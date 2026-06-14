-- The modifier_reference seed is a shared CMS baseline, especially for CSV
-- snapshots that ship no modifier definitions. It does not replace the
-- source-defined JSON metadata match recorded in
-- modifier_definition_match_status.
with base_modifiers as (
    select *
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }}
),

modifier_reference as (
    select *
    from {{ ref('modifier_reference') }}
)

select
    base_modifiers.*,
    upper(base_modifiers.clean_modifier_code) as match_modifier_code,
    modifier_reference.modifier_class,
    modifier_reference.modifier_category,
    modifier_reference.modifier_meaning,
    coalesce(modifier_reference.affects_pro_tech_split, false) as affects_pro_tech_split,
    case
        when base_modifiers.clean_modifier_code is null then 'missing_modifier_code'
        when modifier_reference.modifier_code is not null then 'matched_reference'
        else 'no_reference'
    end as modifier_reference_status
from base_modifiers
left join modifier_reference
    on upper(base_modifiers.clean_modifier_code) = modifier_reference.modifier_code
