# External Data Enrichment For Gold

Status: recommendation — not yet implemented

This document ranks external data sources that can materially improve future
Gold analytics. It focuses on sources that are authoritative, publicly
available, repeatable to ingest, and joinable to entities already present in
Silver.

## Recommendation

The highest-value external-data investment is not a large collection of
independent dimensions. It is a reviewed facility-identity bridge:

```text
hospital_id <-> CMS Certification Number (CCN) <-> Type-2 NPI
            <-> CMS enrollment identifiers <-> address/FIPS geography
```

Most valuable hospital datasets join on CCN, while this project currently uses
a local `hospital_id` and source-reported Type-2 NPIs. Build and review that
bridge first. It unlocks hospital quality, cost reports, Medicare utilization
and payment benchmarks, health-system affiliation, and geography enrichment.

After the bridge exists, prioritize:

1. CMS Care Compare hospital quality and patient-experience data.
2. CMS HCRIS hospital cost reports.
3. CMS Medicare inpatient/outpatient utilization and payment data.
4. Census/CDC geography and community-context data.
5. CMS/FDA code and payment-system reference files.

These sources directly support the planned Gold questions: whether higher-priced
hospitals have better outcomes, how negotiated prices compare with costs and
Medicare benchmarks, how prices vary across markets, and which services are
actually comparable.

## Ranked Source Backlog

Scores use `high`, `medium`, and `low` relative to this project's current
architecture and intended Gold use cases.

| Priority | Source | Primary join | Analytics value | Integration effort |
|---|---|---|---|---|
| 0 | CMS Hospital General Information + NPPES + CMS provider enrollment | reviewed CCN/NPI/address bridge | high, because it unlocks nearly every hospital enrichment | medium |
| 1 | CMS Care Compare hospital datasets | CCN + measure period | high | low after Priority 0 |
| 1 | CMS HCRIS hospital cost reports | CCN + fiscal year | high | medium |
| 1 | Medicare inpatient/outpatient utilization and payment data | CCN + DRG/APC + year | high | medium |
| 1 | Census ACS + CDC/ATSDR SVI | geocoded facility address to FIPS/tract | high | medium |
| 2 | AHRQ Compendium of U.S. Health Systems | CCN + year | medium-high | low after Priority 0 |
| 2 | CMS code and payment reference files | normalized code + effective period | high for service analytics | medium |
| 2 | FDA NDC Directory | canonical NDC + effective period | medium | low after NDC normalization |
| 3 | Marketplace/Medicaid payer reference data | reviewed payer identity + state/year | medium | high |
| 3 | Hospital Price Transparency enforcement actions | reviewed hospital identity + action date | narrow but useful | medium |

## Priority 0: Facility Identity Bridge

### Sources

- [CMS Hospital General Information](https://data.cms.gov/provider-data/dataset/xubh-q36u)
  provides CCN (`facility_id`), name, address, hospital type, ownership,
  emergency-services status, and summary quality fields.
- [NPPES downloadable files](https://download.cms.gov/nppes/NPI_Files.html)
  provide Type-2 NPI legal names, other names, taxonomies, primary and additional
  practice locations, and update/deactivation evidence. NPPES publishes monthly
  full files and weekly updates.
- [CMS Medicare Fee-for-Service Public Provider Enrollment hospital data](https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/medicare-fee-for-service-public-provider-enrollment-hospital-enrollments)
  and related ownership files provide additional enrollment and ownership
  evidence.

### Why It Comes First

The bundled registry has canonical name, state, broad type, health system, and
MRF URL, but it has no CCN, canonical address, county, ZIP, coordinates, or
reviewed NPI-to-facility relationship. Source-reported Type-2 NPIs are valuable
evidence but may represent a hospital unit, multiple locations, or a broader
organization.

Do not infer a CCN from a single fuzzy name match. Create a reviewed bridge with
match evidence and validity dates.

Suggested entities:

```text
slv_core__facility_identities
  hospital_id
  ccn
  identity_valid_from
  identity_valid_to
  match_status
  match_method
  evidence_source
  evidence_notes

slv_core__facility_npis
  hospital_id
  ccn
  npi
  npi_relationship_type
  relationship_valid_from
  relationship_valid_to
  match_status
  evidence_source
```

The identity bridge should support one hospital to many NPIs and should not
assume that one NPI always maps to one physical facility.

## Priority 1: Hospital Context

### CMS Care Compare

[CMS Provider Data Catalog hospital datasets](https://data.cms.gov/provider-data/topics/hospitals)
include facility-level quality measures such as mortality, readmissions,
complications, patient safety, infections, timely/effective care, and patient
experience. The Hospital General Information file also carries useful summary
ratings and counts.

Recommended model shape:

```text
dim_quality_measure
fact_hospital_quality_measure
  ccn
  measure_id
  measure_period_start
  measure_period_end
  score
  compared_to_national
  denominator_or_case_count
  footnote
```

Gold value:

- Compare price position with outcomes and patient experience.
- Build peer groups using CMS hospital type and ownership.
- Avoid reducing quality to one overall rating by preserving measure grain.

Caveat: measure periods differ and many values are suppressed or unavailable.
Gold should expose measurement period, denominator, and footnote fields.

### HCRIS Cost Reports

[CMS HCRIS cost reports](https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports)
contain annual facility characteristics, utilization, costs and charges by cost
center, Medicare settlement data, and financial statement data for
Medicare-certified institutional providers.

Recommended model shape:

```text
fact_hospital_financial_year
  ccn
  fiscal_year_start
  fiscal_year_end
  beds
  inpatient_days
  discharges
  total_cost
  total_charges
  net_patient_revenue
  operating_margin
  cost_to_charge_ratio
```

Gold value:

- Add hospital scale, utilization, and financial peer groups.
- Compare price levels with cost-to-charge ratios and operating characteristics.
- Distinguish small critical-access facilities from large teaching hospitals.

Caveat: HCRIS is reported data, is revised over time, and has a complex
worksheet/line/column structure. Preserve report version and source coordinates
for every derived metric.

### Medicare Utilization And Payment Benchmarks

[Medicare inpatient hospital data](https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals)
and [Medicare outpatient hospital data](https://data.cms.gov/provider-summary-by-type-of-service/medicare-outpatient-hospitals)
provide service-level utilization, submitted charges, and payment aggregates.

Recommended model shape:

```text
fact_medicare_service_benchmark
  ccn
  service_year
  setting
  code_system
  code
  discharges_or_services
  average_submitted_charge
  average_total_payment
  average_medicare_payment
```

Gold value:

- Calculate negotiated-rate-to-Medicare and cash-to-Medicare ratios.
- Add a utilization signal so service baskets favor commonly delivered care.
- Compare MRF reported amounts with observed Medicare payment aggregates.

Caveat: these are aggregated Medicare fee-for-service observations, not
commercial allowed amounts or a universal fair-price standard. Align inpatient
DRGs and outpatient APCs only when the MRF setting and billing context support
the comparison.

### Geography And Community Context

- [Census ACS 5-year data](https://www.census.gov/data/developers/data-sets/acs-5year.html)
  provide population, income, insurance coverage, poverty, age, and other
  community measures.
- [CDC/ATSDR Social Vulnerability Index](https://www.atsdr.cdc.gov/place-health/php/svi/index.html)
  provides tract- and county-level social-vulnerability measures.

Build a canonical facility address and geocode it to latitude/longitude, county
FIPS, tract FIPS, ZIP/ZCTA, Core-Based Statistical Area, and rural/urban
classification before joining community data.

Gold value:

- Replace state-only comparisons with market and community comparisons.
- Analyze price variation by metro area, rurality, income, insurance coverage,
  and social vulnerability.
- Define more defensible peer groups and market coverage metrics.

Caveat: a hospital's physical location is not its complete patient market.
Geographic dimensions describe facility context unless patient-origin data is
added later.

## Priority 2: Systems, Codes, And Payment References

### AHRQ Compendium Of U.S. Health Systems

The [AHRQ Compendium](https://www.ahrq.gov/chsp/data-resources/compendium.html)
publishes annual system and hospital files that describe health-system
affiliation and system characteristics.

Gold value:

- Replace the registry's manually entered `health_system` label with a
  time-aware, externally supported affiliation.
- Compare within-system and between-system pricing.
- Add system size and structure to hospital peer groups.

Keep the registry value as reviewed local metadata; do not overwrite it
silently when AHRQ disagrees or lacks coverage.

### CMS Code And Payment References

Useful public references include:

- [CMS HCPCS quarterly public-use files](https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update)
  for Level II code descriptions and effective dates.
- [CMS IPPS final-rule files](https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2026-ipps-final-rule-home-page)
  for MS-DRG definitions, relative weights, wage-index inputs, and provider
  payment context.
- CMS OPPS/APC addenda and fee-schedule files for outpatient service grouping
  and payment context.
- CMS ICD-10-CM/PCS files for code descriptions and hierarchy.

Recommended dimensions:

```text
dim_billing_code
dim_service_group
dim_payment_system_code
```

Gold value:

- Make code-backed services human-readable and groupable.
- Create defensible inpatient and outpatient service baskets.
- Add relative-weight and payment-system context to price comparisons.

Important licensing caution: CPT Level I descriptions are copyrighted by the
American Medical Association. Do not redistribute CPT descriptions unless the
project has the required license. A public HCPCS Level II source does not solve
the CPT licensing constraint.

### FDA NDC Directory

The [FDA NDC Directory](https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory)
provides daily-updated product and package listing data with downloadable files
and an API.

Gold value:

- Add labeler, product name, active ingredient, dosage form, route, and package
  information to canonical NDCs.
- Support drug-family grouping and distinguish product/package identities.

Caveat: directory inclusion does not imply FDA approval, reimbursement
eligibility, or current market availability. Preserve FDA status and marketing
dates.

## Lower-Priority Sources

### Payer And Plan References

Marketplace HIOS issuer/product files, state Medicaid managed-care enrollment
reports, and similar references can enrich the existing canonical payer model.
They are lower priority because observed MRF payer strings rarely carry a stable
external identifier. Joining them requires continued reviewed identity and
context mapping rather than a deterministic bulk join.

### Hospital Price Transparency Enforcement Actions

CMS enforcement-action records could support a narrow compliance-events fact.
Use them only for documented actions. Do not infer legal noncompliance from this
project's completeness or usability scores.

## Sources Not Recommended As Initial Dimensions

- Transparency in Coverage files: valuable for a separate payer-rate product,
  but extremely large and outside the current hospital-MRF scope.
- Commercial hospital registries and AHA survey data: potentially valuable, but
  licensing and redistribution constraints make them poor first dependencies.
- Claims data requiring a data-use agreement: analytically powerful, but not a
  repeatable public-source enrichment for this repository.
- A universal cross-payer plan taxonomy: observed plan names do not provide
  stable identifiers for a reliable national join.

## Implementation Architecture

External data should not be committed as dbt seeds when it is large, frequently
updated, or time-varying. Treat it as independently snapshotted source data:

```text
data/reference/raw/{source_name}/{release_date}/...
data/reference/bronze/{source_name}/release_date=.../*.parquet
```

Record source URL, release date, retrieval timestamp, file hash, schema version,
and license/terms metadata. Normalize external sources in dedicated dbt staging
and Silver Core models. Gold should consume conformed dimensions and benchmark
facts rather than joining raw external files directly.

Recommended source-layer families:

```text
transform/models/staging/reference/
transform/models/silver/core/facility_identity/
transform/models/silver/core/reference/
transform/models/gold/
```

Use effective dates or reporting periods on every time-varying external fact.
Do not attach the latest available quality, ownership, cost, or affiliation
record to historical MRF snapshots without an explicit as-of rule.

## Phased Delivery

### Phase 1: Unlock Hospital Enrichment

1. Add reviewed CCN and canonical-address fields through a facility-identity
   bridge.
2. Validate source-reported Type-2 NPIs against NPPES taxonomy and location
   evidence.
3. Ingest Hospital General Information and one Care Compare quality family.
4. Add a first `dim_hospital` or hospital-profile Gold mart with identity,
   ownership, type, quality period, and lineage.

Success criterion: at least 90% of active registry hospitals have a reviewed CCN
match, and unmatched/ambiguous facilities appear in a review queue.

### Phase 2: Add Financial And Market Context

1. Ingest selected HCRIS metrics with source-coordinate lineage.
2. Geocode canonical hospital addresses and add county/tract/market dimensions.
3. Add selected ACS and SVI measures.
4. Build hospital peer groups and price-versus-quality/cost marts.

### Phase 3: Add Service Benchmarks

1. Complete the planned Silver Core billing-code normalization.
2. Add CMS code descriptions and payment-system groupers.
3. Ingest Medicare inpatient/outpatient utilization and payment aggregates.
4. Add negotiated-to-Medicare benchmark ratios and utilization-weighted service
   baskets in Gold.

### Phase 4: Extend Carefully

Add AHRQ health-system history, NDC product enrichment, payer reference data,
and documented enforcement events only after the first three phases show which
dimensions materially improve analysis.

## Decision Summary

Build the CCN/NPI/address identity bridge first. Then ingest Care Compare,
HCRIS, Medicare utilization/payment, and geography data. Those sources have the
best combination of analytical value, public availability, authoritative
provenance, and compatibility with the Gold layer already proposed for this
project.
