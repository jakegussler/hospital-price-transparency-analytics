# CMS Validation Rules

Validation severity and Silver exclusion are independent. The rule registry's
`disposition` controls routing: `exclude_entity` removes only the failing entity
and descendants, `report_only` preserves Silver rows, and
`already_quarantined` reports structural records removed by the parser.

This document inventories the validation rules currently enforced by
`src/hpt/ingest/cms_json_models.py` and the JSON parser fallback path in
`src/hpt/parsers/json_mrf.py`. It is the Stage 1 reference for moving CMS
conformance checks from Python/Pydantic into dbt while keeping Pydantic as a
structural gatekeeper.

The companion machine-facing registry is
`docs/refactor/json-validation-to-dbt/rule-registry.md`.

## Boundary

Pydantic currently does two different jobs:

- Structural parsing: verifies that JSON charge records have the containers and
  scalar fields needed to explode source JSON into Bronze child rows.
- CMS value validation: enforces numeric parseability, positivity, accepted
  values, date/NPI/state formats, and conditional requirements.

The refactor should keep only structural parsing in Pydantic. Structural
failures cannot become well-formed Bronze rows and should continue to be
quarantined with `json_record_parse_diagnostics`. Value validation should move
to dbt so Bronze remains source-faithful and both JSON and CSV use one
queryable validation layer. Unless otherwise noted, CMS rules that generate a
deficiency are proposed as `error` severity (a hard CMS requirement failure).
Whether Silver excludes the failing entity is determined separately by
`disposition`; Bronze always retains the source rows.

## Citation Shortcuts

- JSON v3 dictionary:
  `docs/cms_reference/hospital-price-transparency/documentation/JSON/README.md`
- JSON v3 schema:
  `docs/cms_reference/hospital-price-transparency/documentation/JSON/schemas/V3.0.0_Hospital_price_transparency_schema.json`
- JSON v2.2 dictionary:
  `docs/cms_reference/hospital-price-transparency/archive/documentation/JSON/v2.2_README.md`
- JSON v2.2 schema:
  `docs/cms_reference/hospital-price-transparency/archive/documentation/JSON/schemas/V2.2.1_Hospital_price_transparency_schema.json`
- JSON v2.1 dictionary:
  `docs/cms_reference/hospital-price-transparency/archive/documentation/JSON/v2.1_README.md`
- JSON v2.1 schema:
  `docs/cms_reference/hospital-price-transparency/archive/documentation/JSON/schemas/V2.1.0_Hospital_price_transparency_schema.json`
- CSV v3 dictionary:
  `docs/cms_reference/hospital-price-transparency/documentation/CSV/README.md`
- CSV state codes:
  `docs/cms_reference/hospital-price-transparency/documentation/CSV/state_codes.md`
- CSV templates:
  `docs/cms_reference/hospital-price-transparency/documentation/CSV/templates/`

## Structural Rules That Stay In Pydantic

These are required to build Bronze rows without guessing source structure. They
may also be mirrored in dbt for completeness, but Pydantic remains the first
gate.

| Rule ID | Current location | Applies | JSON fields | CSV mapping | Citation | Classification |
|---|---|---|---|---|---|---|
| `root_required_header_shape` | `CMSMRFJson` field definitions | all | `hospital_name`; `last_updated_on`; `version`; `location_name` or v2 `hospital_location`; `hospital_address`; `license_information`; `attestation` or v2 `affirmation`; `type_2_npi`; `standard_charge_information` | row 1/2 header fields | JSON v3 dictionary, JSON Data Attributes, snippet: `Required: Yes`; JSON v3 schema root `required`; CSV dictionary, General Data Elements | Structural. Header records need stable source metadata and array containers. Parser header extraction currently does not instantiate `CMSMRFJson`, so Stage 2 should still validate header conformance in dbt. |
| `attestation_required_fields` | `Attestation` field definitions | 3.0 | `attestation`; `confirm_attestation`; `attester_name` | attestation statement header; row 2 boolean; `attester_name` | JSON v3 dictionary, Attestation Object, snippet: `Required: Yes`; JSON v3 schema `definitions.attestation.required` | Structural for the root model only. Parser stores available header values without root validation. |
| `license_information_required_state` | `HospitalLicensure.state` field definition | all | `license_information.state` | `license_number\|[state]` header suffix | JSON v3 schema `definitions.license_information.required`; state codes doc, snippet: `two-letter abbreviations` | Structural at root/header grain; value membership is semantic and moves to dbt. |
| `standard_charge_information_required_shape` | `StandardChargeInformation` field definitions | all | `standard_charge_information[].description`; `code_information`; `standard_charges` | `description`; code columns; standard charge columns | JSON v3 schema `definitions.standard_charge_information.required`; JSON dictionaries Standard Charge Information Object | Structural. Missing `code_information` or `standard_charges` prevents charge-item fanout. |
| `code_information_required_shape` | `CodeInformation` field definitions | all | `code_information[].code`; `code_information[].type` | `code\|[i]`; `code\|[i]\|type` | JSON v3 schema `definitions.code_information.required`; CSV Conditional Requirement 3 | Structural for JSON row explosion; accepted code type values are semantic. |
| `drug_information_required_shape_when_present` | `DrugInformation` field definitions | all when object present | `drug_information.unit`; `drug_information.type` | `drug_unit_of_measurement`; `drug_type_of_measurement` | JSON v3 schema `definitions.drug_information.required`; JSON dictionary Drug Information Object | Structural when the optional object exists. Numeric positivity and type enum membership are semantic. |
| `standard_charge_required_setting_shape` | `StandardCharge.setting` field definition | all | `standard_charges[].setting` | `setting` | JSON v3 schema `definitions.standard_charges.required`; CSV dictionary required standard charge table | Structural because Bronze `standard_charges` currently carries one scalar setting per charge row. Enum membership is semantic. |
| `modifier_required_shape` | `ModifierInformation` and `ModifierPayerInformation` field definitions | all | `modifier_information[].description`; `code`; `modifier_payer_information`; payer `payer_name`; `plan_name`; `description` | modifier columns and payer-specific modifier description where represented | JSON v3 schema `definitions.modifier_information.required`; JSON v3 schema `definitions.modifier_payer_information.required` | Structural for the optional JSON modifier dimension. |
| `general_contract_provisions_required_shape` | `GeneralContractProvisions.provisions` field definition | all root model use | `general_contract_provisions[].provisions` | `general_contract_provisions` | JSON v3 dictionary General Contract Provisions Object, snippet: `provisions ... Required Yes`; CSV Optional Column Headers | The parser emits source-faithful `general_contract_provisions` Bronze rows (JSON array objects with optional payer/plan; the flat CSV column). `val__header_violations` flags a present provisions object whose `provisions` text is missing or blank, at the file grain. |

## Header And File Rules

### `last_updated_on_iso_date`

Pydantic requires `last_updated_on` to have the literal shape `YYYY-MM-DD` in
`CMSMRFJson.validate_last_updated_on`. CMS v3 says the MRF date must use ISO
8601 and gives `YYYY-MM-DD`; the JSON schema marks the field with `format:
date`. CSV v3 additionally accepts `M/D/YYYY` and `MM/DD/YYYY`, so Stage 2 must
branch by source format.

Classification: semantic format rule. Move to dbt. Severity: `error`.

JSON field: `last_updated_on`. CSV column: `last_updated_on`.

### `type_2_npi_ten_digit_numeric`

Pydantic requires every `type_2_npi` item to be a 10-digit numeric string in
`CMSMRFJson.validate_type_2_npi`. The CMS dictionaries name the field as Type 2
Organizational NPI and require it, but the JSON schema only says string
`minLength: 1`. The 10-digit check is therefore an app invariant based on the
NPI identifier format rather than a direct JSON schema constraint.

Classification: semantic format rule. Move to dbt. Severity: `error`, because
invalid identifiers should not identify Silver hospitals/locations.

JSON field: `type_2_npi[]`. CSV column: `type_2_npi`, pipe-delimited.

### `state_two_letter_format` and `state_valid_usps_code`

Pydantic uppercases `license_information.state` and rejects values that are not
two alphabetic characters in `HospitalLicensure.validate_state`. CMS v3 calls
state an enum and the state-code reference lists valid two-letter state and
territory abbreviations. Pydantic currently does not reject unknown two-letter
values such as `ZZ`; Stage 2 should add that gap as `state_valid_usps_code`.

Classification: semantic format and accepted-value rules. Move to dbt.
Severity: `error`.

JSON field: `license_information.state`. CSV column/header:
`license_number|[state]`.

## Charge Item Rules

### `ndc_requires_drug_information`

`StandardChargeInformation.validate_ndc_drug_requirements` rejects a charge item
when any `code_information.type` is `NDC` and `drug_information` is missing for
schema families 2.2 and 3.0. It does not apply to 2.1 in the current code. CMS
v3 Conditional Requirement 8 says NDC requires drug unit and drug type; the v3
schema expresses this with `if`/`then` on `code_information`. The v2.2
dictionary has the same conditional rule. The v2.1 dictionary and schema do not
define drug information.

Classification: semantic conditional rule. Move to dbt, keyed at charge-item
grain. Severity: `error`.

JSON fields: `code_information[].type`; `drug_information.unit`;
`drug_information.type`. CSV columns: `code|[i]|type`;
`drug_unit_of_measurement`; `drug_type_of_measurement`.

## Code Rules

### `code_type_allowed_values`

The `cms_code_types` seed stores the project-wide CMS code type list, official
CMS display values, standard names, and schema-family applicability. CMS v3
lists the full value set in the JSON dictionary and schema. Older schemas have
smaller lists; dbt validation uses the seed metadata for both the global
accepted-value check and the family-specific enum check.

Classification: semantic accepted-value rule. Move to dbt. Severity: `error`.

JSON field: `code_information[].type`. CSV column: `code|[i]|type`.

Exact family-specific code-type validation is new in dbt and is driven by the
`valid_in_*` flags in `cms_code_types`.

## Drug Rules

### `drug_unit_numeric_parseable` and `drug_unit_positive`

`DrugInformation.parse_unit` converts `unit` through `_to_optional_decimal`;
booleans, non-numeric strings, and unsupported types reject. `validate_unit`
then requires the value to be greater than zero. CMS v3 defines drug unit as a
numeric element and the JSON schema uses `exclusiveMinimum: 0`.

Classification: semantic value rule. Move to dbt. Severity: `error`.

JSON field: `drug_information.unit`. CSV column:
`drug_unit_of_measurement`.

### `drug_type_allowed_values`

The `DrugMeasurementType` enum rejects values outside `GR`, `ME`, `ML`, `UN`,
`F2`, `EA`, and `GM`. CMS v3 and v2.2 list those valid values.

Classification: semantic accepted-value rule. Move to dbt. Severity: `error`.

JSON field: `drug_information.type`. CSV column:
`drug_type_of_measurement`.

## Standard Charge Rules

### `standard_charge_numeric_parseable` and `standard_charge_numeric_positive`

`StandardCharge.parse_numeric_fields` converts `minimum`, `maximum`,
`gross_charge`, and `discounted_cash` to `Decimal`; `validate_numeric_fields`
requires values to be greater than zero. CMS general JSON and CSV instructions
say numeric elements must be positive; JSON schemas use `exclusiveMinimum: 0`.

Classification: semantic value rules. Move to dbt. Severity: `error`.

JSON fields: `standard_charges[].minimum`; `maximum`; `gross_charge`;
`discounted_cash`. CSV columns: `standard_charge|min`; `standard_charge|max`;
`standard_charge|gross`; `standard_charge|discounted_cash`.

### `setting_allowed_values`

The `Setting` enum rejects values other than `inpatient`, `outpatient`, and
`both` on `StandardCharge.setting` and optional `ModifierInformation.setting`.
CMS v3 documents those values for standard charge and modifier setting.

Classification: semantic accepted-value rule. Move to dbt. Severity:
`error`.

JSON fields: `standard_charges[].setting`; `modifier_information[].setting`.
CSV column: `setting`; modifier setting where available.

### `charge_requires_any_standard_charge_value`

`StandardCharge.validate_conditional_requirements` rejects a standard charge
object unless it has at least one of `gross_charge`, `discounted_cash`, or a
payer-specific dollar/percentage/algorithm value in `payers_information`. CMS
v3 Conditional Requirement 2 and v2.2/v2.1 conditional requirements state the
same item/service rule.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `gross_charge`; `discounted_cash`;
`payers_information[].standard_charge_dollar`;
`standard_charge_percentage`; `standard_charge_algorithm`. CSV columns:
`standard_charge|gross`; `standard_charge|discounted_cash`;
`standard_charge|negotiated_dollar`; `standard_charge|negotiated_percentage`;
`standard_charge|negotiated_algorithm`.

### `payer_dollar_requires_minimum_and_maximum`

`StandardCharge.validate_conditional_requirements` rejects a charge when any
payer has `standard_charge_dollar` but the parent charge lacks `minimum` or
`maximum`. CMS v3 Conditional Requirement 4 and JSON schemas require minimum
and maximum when a payer dollar amount is present.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `payers_information[].standard_charge_dollar`; parent `minimum`;
parent `maximum`. CSV columns: `standard_charge|negotiated_dollar`;
`standard_charge|min`; `standard_charge|max`.

### `count_zero_requires_explanation`

For schema family 3.0, `StandardCharge.validate_conditional_requirements`
rejects percentage/algorithm payer rates with `count == "0"` unless either the
payer has `additional_payer_notes` or the parent charge has
`additional_generic_notes`. CMS v3 Conditional Requirement 7 requires an
explanation when count is zero. The JSON schema is narrower and requires
`additional_payer_notes`; the dictionary allows payer-specific or generic notes.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `count`; `standard_charge_percentage`;
`standard_charge_algorithm`; `additional_payer_notes`;
`additional_generic_notes`. CSV columns: `count`; negotiated percentage and
algorithm columns; `additional_payer_notes|[payer_name]|[plan_name]`;
`additional_generic_notes`.

## Payer Rate Rules

### `payer_required_identity_and_methodology`

`PayersInformation` requires `payer_name`, `plan_name`, and `methodology` on
each JSON payer object. CMS v3 marks those Payers Information attributes as
required, and CSV Conditional Requirement 1 requires payer name, plan name, and
methodology when a payer-specific negotiated charge is encoded.

Classification: semantic completeness rule. Move to dbt. Severity: `error`.
Although these fields are important Silver keys, a Bronze row can still preserve
the malformed source record with null/raw values.

JSON fields: `payer_name`; `plan_name`; `methodology`. CSV columns:
`payer_name`; `plan_name`; `standard_charge|methodology`; wide payer and plan
header placeholders.

### `payer_numeric_parseable` and `payer_numeric_positive`

`PayersInformation.parse_decimal_fields` converts
`standard_charge_dollar`, `standard_charge_percentage`, `estimated_amount`,
`median_amount`, `10th_percentile`, and `90th_percentile` to `Decimal`.
Booleans, non-numeric strings, and unsupported types reject. The paired
validator requires parsed values to be greater than zero. CMS general
instructions say numeric values must be positive; schemas use
`exclusiveMinimum: 0` where those numeric fields exist.

Classification: semantic value rules. Move to dbt. Severity: `error`.

JSON fields: the payer numeric fields above. CSV columns:
`standard_charge|negotiated_dollar`;
`standard_charge|negotiated_percentage`; `median_amount`; `10th_percentile`;
`90th_percentile`; wide equivalents with payer and plan placeholders.
`estimated_amount` is JSON v2.2 only.

### `methodology_allowed_values`

The `StandardChargeMethodology` enum rejects values outside `case rate`,
`fee schedule`, `percent of total billed charges`, `per diem`, and `other`.
CMS v3 and v2.2 methodology notes list those values.

Classification: semantic accepted-value rule. Move to dbt. Severity:
`error`.

JSON field: `payers_information[].methodology`. CSV columns:
`standard_charge|methodology` and
`standard_charge|[payer_name]|[plan_name]|methodology`.

### `payer_requires_negotiated_charge`

`PayersInformation.validate_conditional_requirements` rejects each payer object
that lacks all three payer-specific charge values: dollar, percentage, and
algorithm. CMS v3 Conditional Requirement 3 states the same rule for a Payers
Information object.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `standard_charge_dollar`; `standard_charge_percentage`;
`standard_charge_algorithm`. CSV columns: `standard_charge|negotiated_dollar`;
`standard_charge|negotiated_percentage`;
`standard_charge|negotiated_algorithm`.

### `methodology_other_requires_notes`

`PayersInformation.validate_conditional_requirements` rejects
`methodology == "other"` without `additional_payer_notes`. CMS v3 Conditional
Requirement 1 requires an associated explanation for `other`.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `methodology`; `additional_payer_notes`. CSV columns:
`standard_charge|methodology`; `additional_generic_notes` in CSV Tall;
`additional_payer_notes|[payer_name]|[plan_name]` in CSV Wide.

### `v2_2_percentage_or_algorithm_requires_estimated_amount`

For schema family 2.2, Pydantic rejects a payer rate with percentage or
algorithm and no dollar amount unless `estimated_amount` is present. The v2.2
dictionary says percentage rows must encode a corresponding estimated allowed
amount; the v2.2 schema requires `estimated_amount` when percentage or
algorithm is present and dollar is not.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `standard_charge_percentage`; `standard_charge_algorithm`;
`standard_charge_dollar`; `estimated_amount`. CSV mapping: no direct v3 CSV
column for `estimated_amount`; applies to older JSON family records.

### `v3_percentage_or_algorithm_requires_count`

For schema family 3.0, Pydantic rejects percentage or algorithm payer rates
without `count`. CMS v3 Conditional Requirement 5 and the v3 JSON schema
require count in this case.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `standard_charge_percentage`; `standard_charge_algorithm`;
`count`. CSV columns: negotiated percentage/algorithm columns and `count` or
`count|[payer_name]|[plan_name]`.

### `v3_count_nonzero_requires_allowed_amounts`

For schema family 3.0, Pydantic rejects percentage or algorithm payer rates
with `count != "0"` unless `median_amount`, `10th_percentile`, and
`90th_percentile` are all present. CMS v3 Conditional Requirement 6 defines the
same exception when count is zero.

Classification: semantic conditional rule. Move to dbt. Severity: `error`.

JSON fields: `count`; `median_amount`; `10th_percentile`; `90th_percentile`.
CSV columns: `count`; `median_amount`; `10th_percentile`; `90th_percentile`
and wide payer-plan equivalents.

### `v3_count_allowed_format`

`PayersInformation.normalize_count` accepts integers and strings, converts
integer `0` to `"0"`, integers `1` through `10` to `"1 through 10"`, and
integers `11+` to decimal text. It rejects non-string/non-integer values. The
follow-up `validate_count` applies only to family 3.0 and requires exactly
`"0"`, `"1 through 10"`, or whole numbers 11 and greater. CMS v3 count notes
say whole numbers 11 and greater must not use thousands separators.

Classification: semantic format rule. Move to dbt. Stage 3 should stop
normalizing so Bronze preserves source text. Severity: `error`.

JSON field: `count`. CSV columns: `count` and
`count|[payer_name]|[plan_name]`.

## Schema-family Lineage And Structural Diagnostics

`JsonMrfParser._parse_charge_structural` reads the reported source schema
version from snapshot metadata and normalizes it to families `2.1`, `2.2`, or
`3.0`. Pydantic validation is structural-only and family-agnostic, so the
former accepted-row value-validation fallback loop has been replaced with
record-level schema-family inference from version-specific fields. For example,
v2.2 percentage/algorithm rows use `estimated_amount`, while v3.0 rows use
`count`, `median_amount`, `10th_percentile`, and `90th_percentile`.

Accepted records keep both `reported_schema_family` and inferred
`parser_schema_family`. When they differ, `schema_version_mismatch` is true on
`standard_charge_info`; the dbt charge-item validation model turns that flag
into a warn-severity violation.

If structural validation fails, the item is quarantined and a
`json_record_parse_diagnostics` row is emitted with the reported/parser schema
family context and validation summary. Value-level, conditional, enum, and
format issues now reach Bronze and are diagnosed by dbt validation models.

## Current Gaps To Add In dbt

These are CMS rules or schema constraints that the current Pydantic layer does
not fully enforce. They should be added to the dbt validation layer as new
rules.

| Rule ID | Gap | Citation | Proposed severity |
|---|---|---|---|
| `attestation_text_exact` | Pydantic requires attestation fields but does not verify the CMS-required statement text. | JSON v3 schema `definitions.attestation.properties.attestation.const`; JSON v2 schemas `definitions.affirmation.properties.affirmation.const` | `error` |
| `attestation_confirmation_true` | Pydantic accepts any boolean; CMS says `true` is required to meet the attestation regulatory requirement. | JSON v3 dictionary, Attestation Statement; CSV dictionary, Additional Notes for Attestation Statement | `error` |
| `required_header_text_non_empty` | Pydantic strips whitespace but required strings can still be empty. JSON schemas use `minLength: 1` on many required strings. | JSON v3 schema string properties with `minLength: 1` | `error` |
| `charge_item_required_arrays_non_empty` | Pydantic list fields can be empty unless cross-field logic catches them. JSON schemas use `minItems: 1` for key arrays. | JSON v3 schema arrays with `minItems: 1` | `error` |
| `state_valid_usps_code` | Pydantic checks two alphabetic characters but not membership in the CMS state and territory list. | CSV `state_codes.md`; JSON v3 schema `license_information.state.enum` | `error` |
| `code_type_family_specific_enum` | Pydantic uses one code-type superset for all families. Older JSON schemas have smaller accepted sets. | JSON v2.1 and v2.2 schemas `definitions.code_information.properties.type.enum` | `error` |
| `csv_code_pair_required` | Pydantic only covers JSON. CSV requires code/code-type pairing when either side is present. | CSV Conditional Requirements 2 and 3 | `error` |
| `csv_payer_identity_required_with_rate` | Pydantic requires payer identity inside JSON payer objects. CSV has a separate conditional identity rule, especially Tall. | CSV Conditional Requirement 1 | `error` |
| `csv_placeholder_headers_resolved` | Pydantic has no CSV header role. CMS says placeholders such as `[state]`, `[i]`, `[payer_name]`, and `[plan_name]` must be replaced. | CSV Additional CSV Placeholder Notes | `error` |
| `csv_modifier_without_item_minimum_information` | Pydantic covers JSON modifier objects but not CSV's modifier-without-item rule. | CSV Conditional Requirement 11 | `error` |
| `billing_class_allowed_values` | Pydantic stores optional `billing_class` as free text. CMS recommends/defines accepted billing class values. | JSON v3 Optional Data Attributes; CSV Optional Column Headers | `warn` |
