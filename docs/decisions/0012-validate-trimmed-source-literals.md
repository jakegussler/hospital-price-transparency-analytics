# 0012: Validate Trimmed Source Literals

Status: accepted (amended 2026-06-09 to opt payer-rate identity and methodology
fields into sentinel nullification; see the Decision and Consequences sections)

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

Sentinel nullification is allowed only for a documented, field-level decision.
Codes, free-text notes, raw values, and all numeric validation inputs must
preserve populated sentinel literals: the numeric principle above depends on a
populated `N/A` in a dollar field reaching `try_cast` and emitting
`numeric_cast_failed`, and a code or note that happens to read `None` may be a
legitimate value.

### Opted-in fields: payer-rate identity and methodology

`payer_name`, `plan_name`, and `methodology` on the payer-rate path are opted
into `hpt_nullify_sentinel_text`. This applies in the staging models
(`stg_bronze__csv_charge_rows`, `stg_bronze__payers_information`) and, to keep
the derived CSV `source_rate_ordinal` and the rejection-routing logic in parity,
in the validation inputs of `val__payer_rate_violations`.

The justification is grounded in the CMS specification, not convenience:

- The CSV README ("Do not insert a value or any type of indicators (e.g.,
  `N/A`) if the hospital does not have applicable data to encode") defines
  these sentinel tokens as a non-compliant stand-in for a blank field. On these
  fields the token *means absence*, so treating it as null matches CMS intent
  rather than discarding a real value.
- All three fields are CMS-required (`documentation/CSV/README.md` data
  dictionary; `payers_information.required` in the V3.0.0 JSON schema), so a
  nullified sentinel correctly trips the required-identity-and-methodology
  rules instead of passing as a populated value.
- `methodology` is a closed enum (`case rate`, `fee schedule`, `percent of
  total billed charges`, `per diem`, `other`); no sentinel token is a valid
  value, so nullification cannot erase a legitimate methodology.
- None of these fields are numeric, so the numeric-literal principle above is
  untouched. No payer, plan, or methodology is legitimately named by a token in
  the sentinel list.

A nullified `methodology` sentinel is reclassified from `accepted_value_invalid`
(invalid enum value) to `required_field_missing` (no methodology encoded). This
is intentional: per the CMS "do not insert N/A" instruction the value is absent,
not merely malformed. Both dispositions are `exclude_entity`, so the Silver
outcome is unchanged; only the violation diagnostic differs.

Any future opt-in beyond these fields still requires the same kind of
spec-grounded, field-level justification.

## Consequences

- Validation distinguishes missing values from present-but-invalid values.
- Numeric sentinel placeholders become queryable parse failures.
- Source-derived staging and Silver text fields preserve legitimate values that
  happen to match a sentinel word, except for the payer-rate identity and
  methodology fields opted in above.
- Payer/plan/methodology sentinels no longer surface as phantom payer rates,
  alias non-matches, or `unknown`/`n/a` review-queue candidates; rate rows whose
  only payer identity is a sentinel are routed to a CMS-grounded rejection.
- Adding a sentinel-nullification caller requires domain documentation that
  explains why the sentinel cannot be a legitimate value for that field.
