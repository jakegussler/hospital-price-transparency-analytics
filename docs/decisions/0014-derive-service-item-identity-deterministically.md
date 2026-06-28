# 0014: Derive Service Item Identity Deterministically

Status: accepted

## Context

A stable cross-snapshot charge-item identifier is the seam that any future
price-over-time analysis would need: the same charge item must carry the same
identifier across snapshots, and no such identifier exists in the source data
(JSON assigns a per-file ordinal, CSV has only rows, and the Silver Base
`silver_charge_item_id` is snapshot-scoped by design). Building this identity
deterministically keeps that seam open cheaply even though price history itself
is out of v1 scope (decision 0016) — the mechanics are validated and the
identifier is also useful within a single snapshot for item-grain rollups.

Profiling showed charge items are not curatable the way payers are: the local
corpus holds on the order of a million distinct items and hundreds of
thousands of distinct descriptions, so there is no reviewable seed and no
canonical item master. It also showed that code systems split into two
classes: specific clinical codes (CPT, HCPCS, NDC, the DRG family, APC, EAPG,
HIPPS, CDT, CMG) pin an item down, while categorical codes (revenue codes,
CDM, LOCAL) are categories — a single revenue code spans thousands of distinct
items. Descriptions drift across snapshots in word order, punctuation, and a
small set of abbreviations, while ~80% carry meaningful digits.

## Decision

Treat charge-item normalization as deterministic signature engineering in
Silver Core, not curation:

- `slv_core__charge_item_codes` gains `code_is_specific`, an explicit
  whitelist over `canonical_code_system` so unrecognized systems default to
  the safe non-specific value.
- `slv_core__charge_items` (row-preserving, snapshot-grained) adds three
  snapshot-independent content signatures — `code_signature_specific`,
  `code_signature_all`, `drug_signature` — plus a drift-tolerant
  `description_token_signature` (lowercase, expand `w/o`/`w/`/`&`, strip
  punctuation, sorted distinct tokens) and derives `service_item_id` with an
  explicit basis and confidence: specific codes plus description token plus
  drug signature when specific codes exist; the full code set plus description
  when only categorical codes exist; description and drug alone when uncoded.
- `slv_core__service_items` is the within-hospital cross-snapshot dimension
  (first/last seen, representative description, roll-up counts). It is a
  full-refresh table that reads unscoped inputs and is excluded from the
  snapshot prune, because it spans snapshots by design.
- Identity is audited, not approved: `slv_audit__service_item_overmerge` and
  `slv_audit__code_validation_findings` are finding views under
  `models/silver/audit/` (selector `silver_audit`), with no accept/reject
  workflow.

Deliberately excluded from identity: setting and billing class (charge
context, not item identity), drug quantity (`drug_unit`; profiling found
quantity-only distinctions in 2 groups corpus-wide, and including it would
mint new IDs when hospitals re-baseline pricing quantity), exact descriptions
(token signature instead), and categorical codes when specific codes exist.

Explicitly not built: cross-hospital item identity (`service_group_id`),
curated item seeds or review queues, fuzzy/ML matching, drug base-unit
quantity math, and large abbreviation dictionaries.

## Consequences

- Within-hospital price-over-time tracking has a stable key; its payoff is
  latent until multi-snapshot data exists under `all_snapshots` retention
  (today every hospital holds one snapshot, so `snapshot_count = 1`).
- Identity is reproducible from rules alone; the same inputs always produce
  the same `service_item_id`, and unit-test fixtures pin the exact hashes so
  algorithm changes are loud.
- Items distinguishable only by hospital-internal CDM codes under one generic
  description merge into one `service_item_id` (observed: thousands of
  "noncdm charge record" supply lines under one HCPCS catch-all). This is the
  accepted Option C trade-off: it is visible through `source_item_count` and
  the over-merge audit, and line-grain analysis remains available through
  `silver_charge_item_id`.
- A description change large enough to alter the token set mints a new ID;
  supersession links are out of v1 scope. They belong to the price-history
  extension point (decision 0016) and would only be picked up if real
  multi-snapshot data showed material drift-driven churn. The identity mechanics
  themselves are validated (see `docs/development/multi-snapshot-validation.md`);
  this decision stands as the seam that future history work would build on.
- Cross-hospital comparison stays a Gold code-cohort join, never item
  identity.

Decision 0013 covers the billing-code enrichment this identity design builds on.
The profiling rationale is summarized in this decision so the trade-off remains
reviewable without local planning notes.
