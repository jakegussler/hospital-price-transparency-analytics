{#-
  hpt_derive_plan_type

  Deterministic, conservative structural plan-type classifier.

  Returns a single plan-type token (ppo/hmo/pos/epo/pffs/hdhp) only when
  exactly one such token appears as a whole word in the cleaned plan name.
  Returns NULL when:
    - the input is null/empty,
    - no plan-type token is present, or
    - two or more *distinct* plan-type tokens are present (ambiguous, e.g.
      "ppo hmo" or "cigna ppo hmo"), where assigning one would be misleading.

  Word-boundary matching mirrors the payer_context_rules `token_contains`
  semantics in slv_core__payer_context_matches. It is required for
  correctness: substring matching would wrongly tag coded suffixes like
  "hmox"/"ppox"/"posx" ("commercial hmox - ppox & posx"), dental products
  like "dhmo" (dental HMO), and compact payer codes like "mcrppo".

  This is plan-type *enrichment*: it is a structural attribute comparable
  across payers, never a plan identity, and it is only used as a fallback
  when a payer-context rule did not already supply plan_type. It must never
  be coalesced into market_segment — a plan type alone is not a segment.
-#}
{% macro hpt_derive_plan_type(expression) -%}
{%- set plan_type_tokens = ['ppo', 'hmo', 'pos', 'epo', 'pffs', 'hdhp'] -%}
{%- set src -%}lower(cast({{ expression }} as varchar)){%- endset -%}
case
    when (
        {%- for token in plan_type_tokens %}
        case
            when regexp_matches({{ src }}, '(^|[^a-z0-9]){{ token }}([^a-z0-9]|$)')
                then 1
            else 0
        end{{ ' +' if not loop.last }}
        {%- endfor %}
    ) = 1
    then coalesce(
        {%- for token in plan_type_tokens %}
        case
            when regexp_matches({{ src }}, '(^|[^a-z0-9]){{ token }}([^a-z0-9]|$)')
                then '{{ token }}'
        end{{ ',' if not loop.last }}
        {%- endfor %}
    )
    else null
end
{%- endmacro %}
