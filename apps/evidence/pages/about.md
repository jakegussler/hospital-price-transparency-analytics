---
title: About
hide_title: true
sidebar_position: 8
---

# About This Project

This independent, open-source project ingests hospitals' machine-readable price
files, normalizes their contents, and publishes the results together with the
rules that limit cross-hospital comparisons.

```sql export_stamp
select
  left(max(exported_at_utc), 10) as exported_on,
  max(corpus_label) as corpus_label,
  max(build_id) as build_id
from hpt.public_metadata
```

## Why this exists

Federal rules require hospitals to publish their standard charges, but file
formats and labels vary. This project compares only rows that meet the published
methodology. Rows that do not qualify remain available with a specific reason.

## Scope

- **Corpus:** <Value data={export_stamp} column=corpus_label /> — a
  defined hospital set, listed below. Results apply only to the included
  hospitals and should not be generalized to other markets.
- **Sources:** each hospital's own published standard-charges file, linked
  from its page.
- **Cadence:** data refreshes when the corpus is re-ingested and re-exported;
  the export date and build identifier appear on the overview and
  [downloads](/downloads) pages.

## Hospitals in the current corpus

```sql roster
select
  hospital_display_name,
  '/hospitals/' || hospital_id as hospital_link,
  health_system,
  hospital_type,
  published_last_updated_on
from hpt.hospital_overview
order by hospital_display_name
```

<DataTable data={roster} link=hospital_link>
  <Column id=hospital_display_name title="Hospital" />
  <Column id=health_system title="Health system" />
  <Column id=hospital_type title="Type" />
  <Column id=published_last_updated_on title="File published" />
</DataTable>

## Corrections

If you represent a hospital or insurer and believe a number is wrong, open an
issue in the <a href="https://github.com/jakegussler/hospital-price-transparency-analytics/issues">project repository</a>
with the page URL, the value in question, and, if possible, the corresponding
row in the hospital's published file. We will check the source file, parsing,
normalization rules, and presentation. Confirmed project errors will be
corrected; source-file issues will be identified as such.

## Current site features

The site includes a comparability funnel, hospital report cards, insurer
profiles, methodology and glossary pages, and a download bundle with a data
dictionary. Hospital-level **data confidence** and context-level **comparison
confidence** are separate measures.

## What's planned

- Keeping the Nashville hospital roster and source files current, then adding
  other metros.
- Loading more public-domain code descriptions (HCPCS and APC next).
- Price history once multiple file versions per hospital are retained.
- Better insurer-name matching coverage.

## What this site will not do

Predict your bill, rank hospitals by quality, or assert legal compliance.
Those require data and authority this project does not have — and saying so is
part of the methodology.
