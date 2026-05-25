# 0004: Separate Python Parsing From dbt Modeling

Status: accepted

## Context

Hospital MRFs arrive as heterogeneous JSON, CSV Tall, and CSV Wide files. The
pipeline needs code that can stream large files, inspect source layouts, unpivot
dynamic CSV payer columns, and write source-faithful Bronze tables. It also needs
analytical transformations that can be tested, rebuilt, profiled, and reasoned
about as SQL models.

## Decision

Use Python for source acquisition, snapshot tracking, structural parsing, and
Bronze Parquet writing. Use dbt with DuckDB for semantic normalization in Silver
and analytics-ready modeling in Gold.

## Rationale

Python is the better fit for file-oriented work: streaming downloads, hashing,
compression handling, JSON streaming, CSV sniffing, validation, quarantine, and
CSV Wide unpivoting.

dbt is the better fit for durable modeling: declared dependencies, repeatable SQL
builds, source and model tests, documented grains, and iterative normalization
that does not require reparsing raw files.

Keeping the boundary explicit prevents Bronze parsers from accumulating business
normalization logic and keeps analyst-facing transformations visible in the dbt
DAG.

## Consequences

- Bronze parser outputs should remain structural and source-faithful.
- Python should not canonicalize payers, plans, charge items, or code systems.
- dbt models may clean, type, conform, and test values while preserving raw
  lineage fields.
- Re-running Silver or Gold after mapping changes should not require
  redownloading or reparsing source MRFs.
- Complex matching helpers may be built in Python later, but reviewed canonical
  mappings should be applied in dbt models or seeds.
