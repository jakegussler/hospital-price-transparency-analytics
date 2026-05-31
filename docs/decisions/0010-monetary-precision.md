# 0010: Cast Monetary Amounts To Decimal In dbt

Status: accepted

## Context

Hospital MRFs publish charge amounts across JSON and CSV layouts, including
currency-like values such as gross charge, discounted cash, minimum, maximum,
negotiated dollar, estimated amount, and allowed-amount percentiles.

Originally the JSON Bronze parser wrote these fields as Polars `Float64` (it
streamed with `ijson` using `use_float=True` and converted at the Bronze write
boundary), while the CSV parsers preserved them as raw text. That split meant
JSON lost source precision and original representation before dbt. Both formats
now preserve numeric source values as raw text, so Bronze is source-faithful for
numbers across formats. Bronze is still not the right layer for analytics-grade
monetary arithmetic — that boundary belongs to dbt.

## Decision

Both JSON and CSV Bronze preserve numeric-looking source values as raw text
(Polars `Utf8`) instead of coercing them, keeping Bronze source-faithful. The
JSON parser drops `ijson`'s `use_float=True` so numbers stay `Decimal` through
Pydantic validation, then serializes accepted values to their plain string form
for Bronze. In both formats, monetary amounts are cast to `decimal(18, 4)` in
dbt staging before they flow into Silver.

JSON records are still validated by Pydantic before Bronze. Numeric fields that
the CMS model requires must parse as a valid `Decimal`, so records with invalid
numbers are quarantined rather than written to an accepted Bronze row; the
text-preservation change only affects the representation of *accepted* values.

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

- Staging and Silver monetary arithmetic use fixed-point decimal values.
- JSON Bronze numeric amount/unit/percentage columns are `Utf8` rather than
  `Float64`; accepted values keep their exact source digits (no float round-trip)
  until dbt staging casts them.
- CSV malformed numeric values are no longer coerced to null (or merely logged)
  during parsing; they survive as raw text in Bronze and become null only when
  dbt staging casts them. The `stg_bronze__csv_numeric_parse_diagnostics` model
  emits one row per non-empty raw value that fails the cast, so bad numbers stay
  queryable. ADR 0011 generalizes this into the `validation` schema: the
  `val__standard_charge_violations`, `val__payer_rate_violations`, and
  `val__drug_violations` models preserve the same `numeric_cast_failed`
  diagnostic vocabulary and drive reject-severity Silver filtering.
- JSON keeps its stronger validation path: Pydantic still enforces numeric
  validity before Bronze output, and invalid records are quarantined as JSONL
  and recorded in `json_record_parse_diagnostics`. Because invalid JSON numbers
  are quarantined whole, an equivalent JSON cast-diagnostics staging model would
  only catch accepted records whose text somehow fails staging casts, so none is
  added.
