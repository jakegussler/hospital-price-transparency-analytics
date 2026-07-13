# Architecture Decision Records

These records capture decisions that materially shape the implemented pipeline.
They explain why the current design exists; current operational instructions
live in the architecture and development documentation.

## Foundations And Storage

- [0001 — Use Polars And DuckDB](0001-use-polars-and-duckdb.md)
- [0002 — Use fsspec Storage Abstraction](0002-use-fsspec-storage-abstraction.md)
- [0003 — Bronze Partitioning Strategy](0003-bronze-partitioning-strategy.md)
- [0004 — Separate Python Parsing From dbt Modeling](0004-separate-python-parsing-from-dbt-modeling.md)
- [0010 — Cast Monetary Amounts To Decimal In dbt](0010-monetary-precision.md)

## Silver, Validation, And Identity

- [0005 — Split Silver Base And Silver Core](0005-split-silver-base-and-silver-core.md)
- [0006 — Model All Snapshots In Silver](0006-model-all-snapshots-in-silver.md)
- [0007 — Unify JSON And CSV In Silver Base](0007-unify-json-and-csv-in-silver-base.md)
- [0008 — Use Registry-Backed Hospital Identity](0008-use-registry-backed-hospital-identity.md)
- [0009 — Normalize Payers As Identity Plus Context](0009-normalize-payers-as-identity-plus-context.md)
- [0011 — Add dbt Validation Between Bronze And Silver](0011-dbt-validation-layer.md)
- [0012 — Scope Snapshot-Grained Consumers, Not Staging](0012-scope-snapshot-grained-consumers-not-staging.md)
- [0013 — Normalize Billing Codes As Enrichment](0013-normalize-billing-codes-as-enrichment.md)
- [0014 — Derive Service Item Identity Deterministically](0014-derive-service-item-identity-deterministically.md)
- [0015 — Classify Methodology And Amount Semantics](0015-classify-methodology-and-amount-semantics.md)

## Gold Analytics And Public Reporting

- [0016 — Scope Price History As An Extension Point](0016-scope-history-as-extension-point.md)
- [0017 — Define The Gold Comparability Framework](0017-gold-comparability-framework.md)
- [0018 — Keep The Gold Fact Atomic And Expand Codes Through A Bridge](0018-gold-fact-is-atomic-code-expansion-is-a-bridge.md)
- [0019 — Scope The Active Corpus And Enrich Code Descriptions](0019-scope-active-corpus-and-enrich-code-descriptions.md)
- [0020 — Use Evidence For Public BI](0020-use-evidence-for-public-bi.md)
