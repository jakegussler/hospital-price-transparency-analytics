# 0009: Normalize Payers As Identity Plus Context

Status: accepted

## Context

Hospital MRF payer and plan fields mix several different concepts in a small
number of strings: payer brands, administrators, parent companies, plan types,
market segments, products, networks, government programs, benefit lines, and
state-specific Medicaid or Blue plan context.

For negotiated-rate analysis, the project needs stable payer identities that
support broad comparisons such as Aetna vs. UnitedHealthcare vs. Humana. It also
needs to preserve plan and program detail without turning every product,
network, or state program into a separate payer.

## Decision

Normalize payer data by separating payer identity from payer context.

`canonical_payer_id` identifies the broad payer, payer brand, administrator,
network, or BCBS licensee used for payer-level analysis. It should not encode
market segment, product, network, benefit line, plan type, or state program
context.

Plan and program meaning is stored in separate context columns on Silver Core
payer-rate rows, including:

- `market_segment`
- `program_type`
- `product_or_network_name`
- `subsidiary_or_brand`
- `benefit_line`
- `funding_arrangement`
- `context_state`
- `plan_type`

Use these dbt seeds as the auditable normalization inputs:

- `canonical_payers.csv` defines broad payer identities and parent rollups.
- `payer_aliases.csv` maps cleaned payer names to broad canonical payer IDs.
- `payer_context_rules.csv` classifies payer and plan context after identity is
  resolved.

Context rules enrich rows; they do not replace `canonical_payer_id`.

## Method

Silver Base preserves source payer and plan values and creates deterministic
cleaned fields such as `clean_payer_name` and `clean_plan_name`.

Silver Core resolves payer identity first:

1. `slv_core__payer_alias_matches` matches `clean_payer_name` to active
   `payer_aliases` rows. Inactive rows are retained as documented non-matching
   decisions.
2. The alias match assigns a broad `canonical_payer_id`.
3. `slv_core__payer_rates` joins `canonical_payers` for payer name, parent, and
   payer type metadata.

Silver Core then classifies context:

1. `slv_core__payer_context_matches` applies accepted, active context rules
   using the resolved `canonical_payer_id`, optional `source_clean_payer_name`,
   `clean_plan_name`, and state scope.
2. Ranking prefers state-scoped rules, lower `priority`, stronger match types,
   longer patterns, and deterministic rule IDs.
3. The best context rule populates context fields and explanatory metadata such
   as `payer_context_rule_id`, `payer_context_match_basis`,
   `payer_context_review_status`, and `payer_context_confidence`.

Review queue models identify missing mappings:

- `slv_review_queue__payer_candidates` groups unmatched payer names where
  `canonical_payer_id` is null.
- `slv_review_queue__payer_plan_candidates` groups unmatched payer and plan
  combinations so reviewers can see the plan context attached to unmapped
  payers.

Both review queues expose examples and counts, including `example_state` and
`state_count`, without treating state as part of the default grouping.

## Payer Identity Rules

Use national or regional payer brands as canonical identities when they are the
business entity users compare directly, such as `aetna`, `unitedhealthcare`,
`humana`, `cigna`, `caresource`, `molina`, `wellcare`, and `wellpoint`.

Keep distinct administrators, networks, and payer brands as canonical identities
when they commonly appear as the payer in hospital files and are useful for
analysis, such as `umr`, `surest`, `optum`, `phcs`, and `first_health`.

Do not collapse all payer identities to parent companies. Parent organizations
belong in `payer_parent_id` and `payer_parent_name`, not in
`canonical_payer_id`.

Do not collapse Blue Cross Blue Shield into one national payer. Use
licensee-level canonical IDs where possible, such as `bcbs_tennessee`,
`bcbs_michigan`, `blue_shield_california`, or
`anthem_blue_cross_california`.

## Context Rules

Use context fields for details that are analytically useful but are not payer
identity:

- Medicare Advantage, Medicaid managed care, exchange, commercial, workers
  comp, TRICARE/VA, self-pay, and other government context belong in
  `market_segment`.
- D-SNP, TennCare, Medi-Cal, Federal Employee Program, and VA CCN belong in
  `program_type`.
- Aetna Whole Health, Aetna VHAN, UHC Choice Plus, UHC West, BlueAdvantage, and
  Humana ChoiceCare belong in `product_or_network_name`.
- Aetna Better Health, UnitedHealthcare Community Plan, Humana Military, and
  similar operating brands belong in `subsidiary_or_brand` unless they are being
  used as distinct payer identities.
- Dental, vision, behavioral health, transplant, and similar service areas
  belong in `benefit_line`.
- HMO, PPO, POS, EPO, PFFS, and similar labels belong in `plan_type`.

Unknown product or program context should remain null or `unknown` in context
fields. Do not create payer IDs such as `<payer>_unknown`.

## Rationale

This design preserves the most useful analytical grain for payer comparison
while keeping plan detail queryable. A broad payer dimension makes questions
such as payer presence, price variation, and cross-hospital comparisons easier
to answer without downstream re-rollups.

The seed structure is intentionally small and auditable. Exact alias matching
keeps payer identity deterministic. Context rules preserve explainability
through rule IDs, match basis, review status, and confidence. The review queues
focus maintenance on unmapped values instead of asking maintainers to inspect
every observed payer string.

## Consequences

- `canonical_payer_id` is stable payer identity, not a product or program code.
- Product-specific legacy IDs such as payer plus commercial, Medicare Advantage,
  dental, Medicaid state program, or network suffixes should not be added.
- Context matching cannot override payer identity in the current design.
- Ambiguous cases should remain unmatched and appear in the review queue rather
  than receiving speculative identity overrides.
- Seed updates must include evidence and review metadata because the seeds are
  the payer-normalization audit trail.
- More complex identity-resolution rules should be added only if review queue
  volume proves that aliases and state-scoped mappings are insufficient.
