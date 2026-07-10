---
title: About
hide_title: true
sidebar_position: 8
---

# About This Project

An independent, open-source effort to make hospital price transparency files
actually legible: ingest the machine-readable files hospitals publish,
normalize them carefully, and present them with every comparison limit stated
out loud.

```sql export_stamp
select
  left(max(exported_at_utc), 10) as exported_on,
  max(corpus_label) as corpus_label,
  max(build_id) as build_id
from hpt.public_metadata
```

## Why this exists

Federal rules require hospitals to publish their standard charges, but the
files are large, inconsistent, and easy to over-read. Most presentations of
this data either dump raw tables or overstate what can be compared. This
project takes a third path: **compare only what can honestly be compared, show
everything else with a named reason, and publish the methodology in full.**

## Scope

- **Corpus:** <Value data={export_stamp} column=corpus_label /> — a
  deliberately bounded hospital set, listed below. Metro-bounded corpora keep
  claims checkable; nothing here is a regional or national benchmark.
- **Sources:** each hospital's own published standard-charges file, linked
  from its page.
- **Cadence:** data refreshes when the corpus is re-ingested and re-exported;
  the current export is stamped on every page footer area and on
  [downloads](/downloads).

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

If you represent a hospital or insurer and believe a number is wrong, we want
to know. Open an issue on the project repository (or contact the maintainer)
with the page URL, the value in question, and — if you can — the corresponding
row in your own published file. We will check, in order: the source file
itself, our parsing of it, our normalization rules, and the presentation. If
we erred, we fix and note it below; if the source file drives the number, we
will say that too.

## Release notes

- **{export_stamp[0].exported_on} (build {export_stamp[0].build_id})** —
  redesigned public reports: plain-language labels throughout, the
  comparability funnel, hospital report cards, insurer profiles, a full
  methodology and glossary, and a documented download bundle with a data
  dictionary. Renamed the two confidence measures (hospital-level "data
  confidence" vs. context-level "comparison confidence") so they can no
  longer be confused.

## What's planned

- Growing the corpus (more hospitals, then more metros) — the methodology is
  built to scale without changing.
- Loading more public-domain code descriptions (HCPCS and APC next).
- Price history once multiple file versions per hospital are retained.
- Better insurer-name matching coverage.

## What this site will not do

Predict your bill, rank hospitals by quality, or assert legal compliance.
Those require data and authority this project does not have — and saying so is
part of the methodology.
