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

Reject-severity failures are converted into `val__*_rejections` keysets. Silver
base models anti-join those keysets:

- snapshot/header rejects remove the snapshot from Silver;
- charge-item, code, and drug rejects remove the affected charge item;
- standard-charge rejects remove only the affected standard charge context;
- payer-rate rejects remove only the affected payer rate.

Warn-severity failures remain in Silver and are queryable in validation. Bronze
and staging remain complete and source-faithful.

Pydantic remains responsible for structural JSON parsing until Stage 3 finishes
relaxing value-level validators. JSON quarantine diagnostics are represented in
`val__structural_parse_violations`; value-level JSON violation models are ready
for records that will begin reaching Bronze after Stage 3.

## Consequences

- Bronze is the durable record of source values; Silver is filtered by explicit
  dbt validation keysets.
- CSV numeric diagnostics are preserved and superseded by the broader
  validation models, which emit the same `numeric_cast_failed` diagnostic type.
- Validation statistics (`val_stats__*`) provide pass rates, rule summaries,
  numeric distributions, and warn-level anomaly monitoring.
- Rules without current Bronze row evidence are tracked in
  `val__rule_coverage` rather than silently skipped.
