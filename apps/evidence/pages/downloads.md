---
title: Downloads
hide_title: true
sidebar_position: 7
---

# Downloads & Data Dictionary

Everything this site shows is downloadable. Each table ships as **Parquet**
(typed, compact) and **CSV** (opens anywhere), generated in the same export
that feeds these pages — the files and the site always match.

```sql export_stamp
select
  left(max(exported_at_utc), 10) as exported_on,
  max(corpus_label) as corpus_label,
  max(build_id) as build_id
from hpt.public_metadata
```

<SiteCallout type="scope">
Corpus: <b><Value data={export_stamp} column=corpus_label /></b> · Exported:
<b><Value data={export_stamp} column=exported_on /></b> · Build:
<b><Value data={export_stamp} column=build_id /></b>. The bundle also includes
a <a href="/downloads/README.md">README</a> restating scope and usage rules.
</SiteCallout>

## The tables

```sql downloads
select
  public_table_name,
  case public_table_name
    when 'hospital_overview' then 'One row per hospital: scores, confidence, freshness, coverage counts.'
    when 'service_market_explorer' then 'One row per service context and price type: denominators, market statistics, comparison status.'
    when 'hospital_service_rankings' then 'One row per hospital, service context, and price type: the hospital''s amount vs. four peer groups.'
    when 'payer_contracting_explorer' then 'One row per insurer, hospital, and service context: negotiated rate vs. cash and vs. insurer market.'
    when 'comparison_blocker_summary' then 'One row per file snapshot and blocker reason: blocked-row counts and shares.'
    when 'featured_services' then 'Rule-selected default comparisons (up to 30 rows).'
    when 'market_summary' then 'One corpus-level row: headline counts with correct distinct-count semantics.'
    when 'comparability_funnel' then 'One row per hospital (plus corpus total) and funnel stage: rows surviving each comparison rule.'
    when 'payer_overview' then 'One row per matched insurer: contexts, hospitals, cash-comparison counts.'
  end as what_it_is,
  row_count,
  '/downloads/' || public_table_name || '.parquet' as parquet_link,
  '/downloads/' || csv_file_name as csv_link
from hpt.public_metadata
order by public_table_name
```

<DataTable data={downloads} rows=15>
  <Column id=public_table_name title="Table" />
  <Column id=what_it_is title="What it is" />
  <Column id=row_count title="Rows" fmt=num0 />
  <Column id=parquet_link title="Parquet" contentType=link linkLabel="Parquet ↓" />
  <Column id=csv_link title="CSV" contentType=link linkLabel="CSV ↓" />
</DataTable>

CSVs larger than 25 MB ship gzip-compressed (`.csv.gz`) — most tools open them
directly; otherwise unzip first. Parquet is the recommended format for
analysis.

The data dictionary itself:
[Parquet ↓](/downloads/public_data_dictionary.parquet) ·
[CSV ↓](/downloads/public_data_dictionary.csv)

## Data dictionary

Every column of every table, generated from the same schema documentation the
pipeline tests against.

```sql dictionary
select
  public_table_name,
  column_name,
  column_description,
  table_description
from hpt.public_data_dictionary
order by public_table_name, column_name
```

<DataTable data={dictionary} rows=25 search=true groupBy=public_table_name subtotals=false>
  <Column id=public_table_name title="Table" />
  <Column id=column_name title="Column" />
  <Column id=column_description title="Meaning" />
</DataTable>

## Using this data responsibly

If you analyze or republish these files, carry these rules with you — they are
part of the data's meaning:

- **Scope:** every number is bounded to the corpus above. Do not present
  results as regional or national benchmarks.
- **One price type at a time:** never rank `gross_charge` (list),
  `discounted_cash` (cash), and `negotiated_dollar` (negotiated) against each
  other.
- **Respect the floor:** rows or contexts marked `insufficient_denominator`
  have fewer than 3 hospitals and deliberately carry no market statistics.
  Recomputing statistics on them defeats the methodology.
- **Scores ≠ compliance:** usability scores describe published-file
  usability, not legal compliance or care quality.
- **Prices ≠ bills:** standard charges are not quotes and not out-of-pocket
  costs.

## Citing this data

> Hospital Price Transparency project, "{export_stamp[0].corpus_label}" public
> data export, exported {export_stamp[0].exported_on}
> (build {export_stamp[0].build_id}).

The build identifier pins your citation to the exact pipeline version that
produced the numbers. Methodology for citation:
[/methodology](/methodology).

## What is deliberately not here

The public surface is the documented presentation tables above. Raw hospital
files, intermediate pipeline layers, and the atomic observation-level fact
table are not published in v1 — the aggregates above carry their documented
comparison semantics with them, which is exactly what raw extracts would lose.
