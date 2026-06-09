# 0012: Validate Trimmed Source Literals

Status: accepted

## Context

The original `hpt_clean_text` macro combined whitespace normalization,
lowercasing, and conversion of common sentinel literals such as `N/A`, `None`,
`Unknown`, and `-` to null. Validation presence checks and numeric safe casts
both used that macro.

This caused dbt validation to evaluate transformed values rather than the source
literals preserved in Bronze. Populated numeric placeholders did not emit
`numeric_cast_failed`, and legitimate text values such as a payer literally
named `None` could be treated as missing.

## Decision

CMS validation operates on trimmed source literals:

- SQL null and whitespace-only text are missing.
- Populated literals, including `N/A`, `-`, `None`, and `Unknown`, are present.
- Numeric safe casts trim before `try_cast` but do not nullify sentinel
  literals. Populated non-numeric sentinels therefore emit
  `numeric_cast_failed`.
- Rule-specific comparisons may normalize case or collapse whitespace, but
  sentinel nullification is not part of validation.

The dbt text macros have explicit contracts:

- `hpt_trimmed_text` trims outer whitespace and nullifies only SQL null or blank
  text.
- `hpt_normalize_text` additionally collapses internal whitespace and
  optionally lowercases, while preserving sentinel literals.
- `hpt_nullify_sentinel_text` retains the historical sentinel list behind an
  explicit opt-in API.

Sentinel nullification is allowed only for a documented, field-level Silver
normalization decision. No current source-derived field is opted in. In
particular, payer/plan names, codes, enums, notes, raw values, and validation
inputs must preserve populated sentinel literals.

## Consequences

- Validation distinguishes missing values from present-but-invalid values.
- Numeric sentinel placeholders become queryable parse failures.
- Source-derived staging and Silver text fields preserve legitimate values that
  happen to match a sentinel word.
- Adding a sentinel-nullification caller requires domain documentation that
  explains why the sentinel cannot be a legitimate value for that field.
