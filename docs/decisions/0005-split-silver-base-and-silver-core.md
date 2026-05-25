# 0005: Split Silver Base And Silver Core

Status: accepted

## Context

Silver has to solve two different problems. First, it must make JSON, CSV Tall,
and CSV Wide data queryable through one format-neutral schema. Second, it must
eventually apply canonical business mappings for payers, plans, code systems,
service items, and cross-snapshot identity.

Combining those concerns in one model pass would make early Silver look cleaner,
but it would also mix structural reconciliation bugs with business matching
decisions.

## Decision

Split Silver into two sublayers:

- `silver/base`: typed, cleaned, source-format-neutral models that preserve raw
  values and source lineage.
- `silver/core`: conformed models that apply reviewed canonical mappings,
  cross-snapshot consolidation, and analytics-oriented business identities.

This is an implementation boundary inside Silver, not a separate medallion
layer.

## Rationale

Silver base gives the project useful all-format profiling tables before payer,
plan, and service-item matching rules are mature. It also gives dbt tests a
stable place to verify grains and row reconciliation across Bronze and Silver.

Silver core can then iterate on canonical mappings without changing Bronze
parsers or the structural foundation. This matters because payer and plan strings
are messy, ambiguous, and expensive to merge incorrectly.

## Consequences

- `transform/models/silver/base/` models should keep raw, cleaned, and lineage
  fields even when a later core model will add canonical IDs.
- `transform/models/silver/core/` is the place for reviewed payer, plan, code
  system, and cross-snapshot service item identities.
- A "clean" value means deterministic formatting cleanup, not canonical truth.
- Mapping seeds and review status fields belong with Silver core work.
- Gold models should depend on Silver core when canonical identity is required,
  and may depend on Silver base only for profiling or source-faithful analysis.
