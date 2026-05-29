# 0010: Cast Monetary Amounts To Decimal In dbt

Status: accepted

## Context

Hospital MRFs publish charge amounts across JSON and CSV layouts. The JSON
Bronze parser writes numeric amount fields as Polars `Float64`, including
currency-like values such as gross charge, discounted cash, minimum, maximum,
negotiated dollar, estimated amount, and allowed-amount percentiles. The CSV
Bronze parsers preserve these fields as raw text instead.

This is an explicit Bronze compromise for JSON. JSON parsing streams with
`ijson` and uses float conversion at the Bronze write boundary. CSV parsing, by
contrast, now preserves numeric cells as raw text and leaves casting to dbt
staging. Bronze remains source-faithful structurally, but it is not the right
layer for analytics-grade monetary arithmetic.

## Decision

CSV Bronze preserves numeric-looking cells as raw text (Polars `Utf8`) instead
of coercing them, keeping Bronze source-faithful. JSON Bronze still writes
numeric amount fields as `Float64` (see the caveat in Consequences). In both
cases, monetary amounts are cast to `decimal(18, 4)` in dbt staging before they
flow into Silver.

Use `hpt_safe_decimal` for currency-like amount columns:

- gross charge
- discounted cash
- minimum
- maximum
- negotiated dollar / standard charge dollar
- estimated amount
- median amount
- tenth percentile
- ninetieth percentile

Keep percentage fields and measurement units as `double` because they are not
currency amounts.

## Rationale

`decimal(18, 4)` is enough precision for published hospital prices while keeping
the dbt model behavior easy to inspect in DuckDB. Casting in staging gives
Silver and downstream analysis stable decimal semantics without forcing a
larger parser rewrite.

## Consequences

- Bronze Parquet remains compatible with the existing parser and loader code.
- Staging and Silver monetary arithmetic use fixed-point decimal values.
- CSV malformed numeric values are no longer coerced to null (or merely logged)
  during parsing; they survive as raw text in Bronze and become null only when
  dbt staging casts them. The `stg_bronze__csv_numeric_parse_diagnostics` model
  emits one row per non-empty raw value that fails the cast, so bad numbers stay
  queryable.
- JSON Bronze still converts numbers to floats at parse time because the
  payloads are already typed; that lossy boundary is documented rather than
  hidden.
- A future JSON Bronze precision upgrade would require revisiting the JSON
  streaming parse settings, Pydantic conversion, and Parquet schema.
