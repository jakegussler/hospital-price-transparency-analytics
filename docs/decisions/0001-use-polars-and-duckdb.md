# 0001: Use Polars And DuckDB

Status: accepted

## Context

Hospital MRFs can be large, inconsistent, and published in multiple structures.
The project needs efficient parser-side DataFrame handling and a local analytical
database for downstream modeling.

## Decision

Use Polars in the Python pipeline for parser output construction and Parquet
writing. Use DuckDB as the local analytical database for dbt models and
exploratory analysis.

## Rationale

Polars is a good fit for parser-side batch construction because it is fast,
strict enough to enforce schemas, and integrates well with Parquet.

DuckDB is a good fit for local analytics because it reads Parquet directly,
works well with dbt through `dbt-duckdb`, and avoids requiring a separate
database server during development.

## Consequences

- Parser code should produce schema-stable Polars DataFrames.
- Bronze output should remain Parquet-first.
- dbt models should be written assuming DuckDB semantics unless another
  warehouse target is intentionally added.
- SQL portability matters less than correctness and local reproducibility at
  this stage.
