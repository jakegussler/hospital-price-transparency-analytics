# HPT Glossary

## CMS Machine-Readable File

A CMS hospital price transparency machine-readable file (MRF) is a hospital
published file containing standard charges, negotiated rates, cash prices,
billing codes, payer information, and hospital metadata.

## MRF Layout

The structural family of an MRF:

- JSON: nested CMS schema with arrays for charge information, codes, payers, and
  modifiers.
- CSV Tall: flat charge rows with payer and standard-charge fields represented
  as columns.
- CSV Wide: flat charge rows where payer and plan names are embedded in dynamic
  column headers.

## Hospital Registry

The registry is the configured list of hospital sources the pipeline can
download. It contains stable project hospital IDs, canonical names, source URLs,
and expected source formats.

## Hospital ID

A project-controlled identifier for a hospital source. It is not necessarily a
CMS identifier, NPI, state license number, or source-reported hospital name.

## Snapshot

A versioned record of a downloaded MRF file. Snapshots preserve file hash,
source URL, source filename, and ingest timestamp. Currentness is not stored on
the snapshot; it is derived downstream in dbt from `valid_from` recency.

## Current Snapshot

The active snapshot for a hospital. `hpt ingest` parses current snapshots rather
than arbitrary files.

## File Hash

The SHA-256 hash of downloaded source bytes. Hash comparison is used to avoid
creating duplicate snapshots when a hospital republishes the same file bytes.

## Bronze

The source-faithful parsed data layer. Bronze preserves source structure and raw
values with minimal interpretation.

## Silver

The normalized data layer. Silver resolves entities and semantics: hospitals,
charge items, codes, payers, plans, modifiers, dates, and source quirks.

## Gold

The analytics-ready data layer. Gold exposes conformed dimensions, an atomic
rate-observation fact, a code bridge, comparison/benchmark marts, and
coverage/readiness scorecards.

## Standard Charge

A CMS charge record for an item or service. Depending on context, it can include
gross charge, discounted cash price, negotiated dollar amount, negotiated
percentage, minimum, maximum, estimated allowed amount, methodology, setting, and
billing class.

## Charge Item

The service, drug, or item being priced. JSON has an explicit
`standard_charge_information` parent structure. CSV rows require Silver logic to
identify charge-item groups.

## Billing Code

A code associated with a charge item, such as CPT, HCPCS, NDC, DRG, MS-DRG, or
another source-reported code system.

## Payer

An insurer or payer name as reported by the hospital. Bronze stores raw payer
strings; canonical payer matching belongs in Silver.

## Plan

A payer plan name as reported by the hospital. Bronze stores raw plan strings;
standardization belongs in Silver.

## Modifier

A code that modifies billing or pricing context. JSON can include top-level
modifier definitions and modifier strings attached to standard charges. Bronze
does not resolve those strings into foreign keys.

## Quarantine

Diagnostic output for records that fail validation during parsing. Quarantine is
not the main analytical path, but it helps improve parser coverage and inspect
source-specific issues.

## fsspec

The storage abstraction used for raw files and snapshot metadata. It allows the
same code path to target local files or object stores such as S3 or GCS.

## DuckDB

The expected local analytical database for dbt development and analysis. dbt
reads Bronze Parquet through DuckDB external source definitions.
