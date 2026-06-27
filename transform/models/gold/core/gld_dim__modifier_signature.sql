-- Conformed modifier-group dimension. Grain: one row per modifier_signature =
-- one distinct *set* of modifier codes that attaches to a standard charge.
--
-- A modifier is a multi-valued attribute of an observation (a charge carries a
-- SET of modifiers, not one), so the fact compares and groups on the opaque
-- modifier_signature hash instead of fanning out to individual modifiers. This
-- dimension is what decodes that hash for the BI layer: it expands the signature
-- into its member codes, the human-readable meanings, and the display label,
-- without ever widening the fact or risking a price double-count from a
-- many-to-many modifier bridge. BI joins gld_core__rate_observations (and the
-- marts) to this dimension on modifier_signature.
--
-- Full-refresh table read UNscoped (plain ref) from slv_core__charge_modifiers:
-- a conformed dimension must span every snapshot, so it is excluded from the
-- snapshot prune and never added to hpt_snapshot_grained_incremental_models().
--
-- CONSISTENCY REQUIREMENT: the signature here MUST be byte-identical to the one
-- on the fact. Both are produced by the hpt_modifier_signature() macro over the
-- non-null modifier codes on a standard charge (here match_modifier_code, which is
-- upper(clean_modifier_code) — the same macro that slv_core__rate_modifier_signature
-- and the gld_core__rate_observations rollup call). The no-modifier sentinel
-- comes from hpt_no_modifier_signature() and matches the fact's coalesce default.
-- A relationships test on the fact guards that every fact signature resolves here.
with charge_modifiers as (
    select
        silver_standard_charge_id,
        match_modifier_code,
        modifier_meaning,
        affects_pro_tech_split,
        modifier_reference_status
    from {{ ref('slv_core__charge_modifiers') }}
    where match_modifier_code is not null
),

-- The signature for each standard charge: identical expression to the fact.
charge_signature as (
    select
        silver_standard_charge_id,
        {{ hpt_modifier_signature('match_modifier_code') }} as modifier_signature
    from charge_modifiers
    group by silver_standard_charge_id
),

-- Distinct (signature, member) pairs = the conformed set membership. Member
-- attributes are functionally determined by match_modifier_code (the seed join in
-- slv_core__charge_modifiers keys on a unique modifier_code), so each code appears
-- once per signature and the aggregates below do not fan out.
signature_members as (
    select distinct
        cs.modifier_signature,
        cm.match_modifier_code,
        cm.modifier_meaning,
        cm.affects_pro_tech_split,
        cm.modifier_reference_status
    from charge_modifiers as cm
    inner join charge_signature as cs
        on cm.silver_standard_charge_id = cs.silver_standard_charge_id
),

signature_rollup as (
    select
        modifier_signature,
        count(distinct match_modifier_code) as modifier_count,
        string_agg(
            distinct match_modifier_code,
            '|' order by match_modifier_code
        ) as modifier_codes,
        string_agg(
            match_modifier_code
                || ' (' || coalesce(modifier_meaning, 'Unknown modifier') || ')',
            ' + ' order by match_modifier_code
        ) as modifier_label,
        string_agg(
            coalesce(modifier_meaning, 'Unknown modifier'),
            ' | ' order by match_modifier_code
        ) as modifier_meanings,
        bool_or(affects_pro_tech_split) as has_pro_tech_split_modifier,
        bool_or(modifier_reference_status <> 'matched_reference')
            as has_unreferenced_modifier
    from signature_members
    group by modifier_signature
)

select
    modifier_signature,
    modifier_count,
    modifier_codes,
    modifier_label,
    modifier_meanings,
    has_pro_tech_split_modifier,
    has_unreferenced_modifier,
    false as is_no_modifier_member
from signature_rollup

union all

-- Sentinel for charges with no modifiers; matches the fact's
-- coalesce(..., md5('<no_modifiers>')) default so those observations join here.
select
    {{ hpt_no_modifier_signature() }} as modifier_signature,
    0 as modifier_count,
    cast(null as varchar) as modifier_codes,
    'No modifiers' as modifier_label,
    cast(null as varchar) as modifier_meanings,
    false as has_pro_tech_split_modifier,
    false as has_unreferenced_modifier,
    true as is_no_modifier_member
