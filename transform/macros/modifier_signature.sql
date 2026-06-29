{# Canonical modifier-set signature: md5 of the sorted, distinct, '|'-joined
   modifier codes on a standard charge. This is the SINGLE source of truth for the
   signature shape so every producer emits byte-identical keys —
   slv_core__rate_modifier_signature (payer-rate scope, from slv_base), the
   gld_fct__rate_observations rollup (standard-charge scope), and
   gld_dim__modifier_signature (the decode dimension). Change the shape here and
   all three move together.

   modifier_code_expr: a NORMALIZED (uppercased) modifier-code column/expression —
   upper(clean_modifier_code) in Silver Base, or match_modifier_code in Silver/Gold
   Core (which is defined as upper(clean_modifier_code)). The caller is responsible
   for filtering null codes; this is an aggregate, used in a grouped select. #}
{% macro hpt_modifier_signature(modifier_code_expr) -%}
    md5(
        string_agg(
            distinct {{ modifier_code_expr }},
            '|' order by {{ modifier_code_expr }}
        )
    )
{%- endmacro %}


{# The sentinel signature for a charge/rate with no modifiers. Producers coalesce
   to this so "no modifiers" is a single joinable cohort value, and it is the
   explicit member key in gld_dim__modifier_signature. Pairs with
   hpt_modifier_signature above. #}
{% macro hpt_no_modifier_signature() -%}
    md5('<no_modifiers>')
{%- endmacro %}
