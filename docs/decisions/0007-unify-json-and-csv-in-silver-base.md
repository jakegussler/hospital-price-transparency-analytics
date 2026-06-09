# 0007: Unify JSON And CSV In Silver Base

Status: accepted

## Context

CMS MRF formats represent similar concepts with different structures. JSON files
have nested charge items, standard charges, payer rows, codes, modifiers, and
optional modifier definitions. CSV Tall and CSV Wide files arrive as flatter
rows, and CSV Wide requires parser-side unpivoting before Bronze.

Downstream models should not need separate JSON, CSV Tall, and CSV Wide query
paths for core charge analysis.

## Decision

Silver base models use a dual-path pattern: build JSON and CSV branches at their
native grains, normalize them to a shared set of columns, and `UNION ALL` them
into format-neutral tables.

The core foundation tables are:

- `slv_base__charge_items`
- `slv_base__standard_charges`
- `slv_base__charge_item_codes`
- `slv_base__payer_rates`
- `slv_base__modifiers`
- `slv_base__modifier_payer_info`
- `slv_base__charge_modifier_declarations`
- `slv_base__charge_modifier_members`
- `slv_base__payer_rate_modifiers`

CSV rows are bridged to synthesized charge items through
`slv_base__csv_charge_row_items`. Standalone CSV modifier rules are excluded
from that bridge and instead enter `slv_base__modifiers`.

## Rationale

JSON already has a charge item parent. CSV does not, so Silver has to synthesize
snapshot-scoped item identity from row values such as description, code set, and
drug attributes. Keeping that as an explicit bridge makes the grouping auditable
and lets payer-rate rows preserve their original row lineage.

Using dual branches also keeps source-specific rules visible. JSON-specific
ordinal fields and CSV-specific row ordinals can be preserved without forcing a
false one-to-one correspondence between the formats.

## Consequences

- Every format-neutral Silver base model should preserve `source_format`.
- JSON source IDs and ordinals should remain available where the JSON source
  provides them.
- CSV `row_ordinal` lineage should be preserved even when rows group into a
  synthesized charge item or standard charge context.
- Full modifier combinations are authoritative declarations; ordered member
  tokens and accepted payer-rate relationships use separate Silver models.
- CSV charge item signatures are snapshot-scoped structural identifiers, not
  reviewed cross-snapshot service identities.
- Reconciliation tests should compare Bronze JSON and CSV source grains to their
  corresponding Silver base outputs.
