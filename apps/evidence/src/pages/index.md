# Nashville Hospital Price Transparency

This public report is bounded to the current Nashville-metro corpus. Readiness
scores summarize published-data usability for comparison work; they are not
legal compliance scores.

```sql export_metadata
select
  max(exported_at_utc) as exported_at_utc,
  max(corpus_label) as corpus_label
from hpt.public_metadata
```

```sql market_summary
select
  count(*) as hospital_count,
  count(distinct snapshot_id) as current_snapshot_count,
  median(overall_readiness_score) as median_readiness_score,
  sum(benchmark_services_meeting_floor) as benchmark_services_meeting_floor,
  sum(matched_payer_count) as matched_payer_count
from hpt.hospital_overview
```

```sql trust_bands
select
  trust_band,
  count(*) as hospital_count
from hpt.hospital_overview
group by 1
order by hospital_count desc, trust_band
```

```sql featured_services
select
  featured_rank,
  service_display_label,
  amount_kind,
  hospital_count,
  trust_band,
  variation_band,
  median_amount,
  p10_amount,
  p90_amount
from hpt.featured_services
order by featured_rank
```

```sql blocker_categories
select
  blocker_category,
  sum(blocked_row_count) as blocked_row_count,
  sum(classified_row_count) as classified_row_count,
  sum(blocked_row_count)::double / nullif(sum(classified_row_count), 0) as blocked_row_share
from hpt.comparison_blocker_summary
group by 1
order by blocked_row_count desc
```

<Grid cols=3>
  <Value data={market_summary} column=hospital_count title="Hospitals" />
  <Value data={market_summary} column=current_snapshot_count title="Current snapshots" />
  <Value data={market_summary} column=median_readiness_score title="Median readiness" fmt=pct1 />
</Grid>

<DataTable data={trust_bands} />

## Featured Services

Each row carries its hospital denominator and trust band. Percentile statistics
are shown only where the Gold BI mart says the service context meets the
comparison floor.

<DataTable data={featured_services} />

## Comparison Blockers

These categories explain why rows do not qualify for stricter comparison use
cases. The thin-cohort denominator blocker is a service-context status and is
shown on service pages as `insufficient_denominator`.

<BarChart data={blocker_categories} x=blocker_category y=blocked_row_count />
<DataTable data={blocker_categories} />

