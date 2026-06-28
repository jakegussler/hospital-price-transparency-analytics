# 0013: Normalize Billing Codes As Enrichment

Status: accepted

## Context

Downstream price comparison needs billing codes that mean the same thing across
hospitals and snapshots. Profiling the local corpus showed the real obstacles
are narrow: revenue codes and DRGs lose leading zeros, NDCs appear in several
digit/hyphenation layouts, hospital-internal CDM/LOCAL codes look joinable but
are not, and professional/technical component modifiers (`26`/`TC`) silently
change what a dollar amount represents.

Equally important is what the corpus does not show: code-system labels resolve
100% through the `cms_code_types` seed, no NDC item lacks a drug unit, and the
dominant drug units are count/activity units with no shared conversion base.

## Decision

Normalize billing codes in Silver Core as row-preserving enrichment over
source-faithful Silver Base, never as a row-inclusion gate, mirroring the payer
identity-plus-context architecture (decision 0009):

- `slv_core__charge_item_codes` (code grain) adds `match_code` (per-system
  zero-padding for fixed-width numeric systems: revenue codes and APC to 4
  digits, the DRG family to 3), `code_format_status`,
  `code_cross_hospital_comparable` (false for CDM/LOCAL), and NDC canonical-11
  fields. 10-digit NDCs are padded only when the hyphen layout (4-4-2, 5-3-2,
  5-4-1) discloses the short segment; ambiguous and malformed values are
  flagged, never guessed.
- `slv_core__payer_rates` gains `modifier_signature` (sorted-set hash with a
  `<no_modifiers>` sentinel), `modifier_count`, and denormalized
  `clean_setting`/`clean_billing_class`, making the rate row a self-contained
  comparable unit for everything except the code.
- `slv_core__charge_modifiers` and `slv_core__drug_information` enrich
  modifiers and drug units through two small CMS-reference seeds
  (`modifier_reference`, `drug_unit_aliases`). `affects_pro_tech_split` names
  the `26`/`TC` split so Gold can refuse to aggregate across it.
- `slv_review_queue__code_system_candidates` and
  `slv_review_queue__modifier_candidates` turn future unrecognized values into
  curation signals instead of silent gaps.

There is deliberately no single primary code per rate: most items carry 2–4
codes from different systems, and the right comparison axis is
analysis-dependent. Cohort assembly is a Gold join over the per-code and
per-rate building blocks.

## Consequences

- `clean_code` stays source-faithful; all matching uses derived fields.
- Malformed, ambiguous, hospital-local, and unknown-system codes keep their
  rows and receive a status; analytics filter by status when needed.
- A `code_system_aliases` seed is explicitly deferred until the code-system
  review queue shows recurring volume.
- Cross-unit drug quantity conversion is explicitly out of scope; quantities
  are only comparable within `drug_unit_group`, and the dominant groups
  (count, activity) are not convertible at all.
- CDM/LOCAL codes remain valid for within-hospital, cross-snapshot analysis;
  they are only excluded from cross-hospital cohorts via the comparability
  flag.

The data profile behind these choices is intentionally summarized here so the
decision remains reviewable without local planning notes.
