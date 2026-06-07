# 0011: Add dbt Validation Layer Between Bronze And Silver

Status: accepted

## Context

JSON ingest has historically used Pydantic for both structural parsing and CMS
value validation. That meant malformed JSON values were quarantined before they
could reach Bronze, while CSV values stayed source-faithful and were diagnosed
in dbt. This created inconsistent behavior across source formats and made row-
level validation review harder.

## Decision

dbt now owns CMS conformance validation in a dedicated `validation` schema. The
seed `cms_validation_rules` is the rule registry, and `val__*` models emit one
row per failing value with source keys, severity, grain, diagnostic type, and
CMS citation metadata.

Severity describes the seriousness of a finding. The separate rule-registry
`disposition` controls Silver filtering:

- `exclude_entity` creates an exact-grain rejection key;
- `report_only` keeps the finding queryable without excluding Silver data;
- `already_quarantined` reports a structural parser failure whose record never
  reached Bronze.

Silver filtering is downward-only. A rejected parent disappears with its
descendants through normal parent joins, while rejected children never remove
their parents or siblings. File/header findings are report-only, so snapshots
and unrelated charge data always remain available.

Warn-severity and report-only failures remain in Silver and are queryable in
validation. Bronze and staging remain complete and source-faithful.

Pydantic remains responsible only for structural JSON parsing. Stage 3 removed
Python value-level, conditional, enum, and format validators, so malformed JSON
values now reach Bronze as raw text. JSON quarantine diagnostics are represented
in `val__structural_parse_violations`; value-level JSON violation models now
operate on accepted Bronze rows.

## Consequences

- Bronze is the durable record of source values; Silver is filtered by explicit
  exact-grain dbt validation keysets.
- JSON and CSV now share the same validation authority: Pydantic no longer
  drops whole JSON records for CMS semantic/value failures.
- CSV numeric diagnostics are preserved and superseded by the broader
  validation models, which emit the same `numeric_cast_failed` diagnostic type.
- Validation statistics (`val_stats__*`) provide pass rates, rule summaries,
  numeric distributions, and warn-level anomaly monitoring.
- Rules without current Bronze row evidence are tracked in
  `val__rule_coverage` rather than silently skipped.
