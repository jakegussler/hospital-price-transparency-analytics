---
title: Hospitals
hide_title: true
sidebar_position: 2
---

# Hospital Scoreboard

How usable is each hospital's published price file? The **data usability
score** (0–100) combines five components: file freshness, billing-code
coverage, dollar-amount coverage, insurer-name matching, and
comparison-readiness. [How the score works.](/methodology/scores)

<SiteCallout type="caution">
These scores describe the published <b>data file</b>, not the hospital's care,
and they are not legal-compliance findings. A lower score often reflects file
format or labeling choices.
</SiteCallout>

```sql hospitals
select
  hospital_display_name,
  '/hospitals/' || hospital_id as hospital_link,
  health_system,
  hospital_type,
  overall_readiness_score,
  case data_confidence_band
    when 'high' then 'High'
    when 'moderate' then 'Moderate'
    when 'limited' then 'Limited'
    else 'Low'
  end as data_confidence,
  case freshness_bucket
    when '<=90d' then 'Within 90 days'
    when '<=180d' then 'Within 180 days'
    when '<=365d' then 'Within 1 year'
    when '>365d' then 'Over 1 year old'
    else 'Unknown'
  end as file_recency,
  published_last_updated_on,
  freshness_score,
  code_coverage_score,
  amount_coverage_score,
  payer_mapping_score,
  comparison_readiness_score,
  distinct_comparable_codes,
  matched_payer_count
from hpt.hospital_overview
order by overall_readiness_score desc, hospital_display_name
```

<BarChart
  data={hospitals}
  x=hospital_display_name
  y=overall_readiness_score
  swapXY=true
  yFmt=pct0
  yMax=1
  title="Data usability score by hospital"
/>

Click a hospital for its full report card: score breakdown, what it published,
its comparability funnel, insurer contracts, and why rows were blocked.

<DataTable data={hospitals} link=hospital_link rows=25 search=true>
  <Column id=hospital_display_name title="Hospital" />
  <Column id=health_system title="Health system" />
  <Column id=data_confidence title="Data confidence" />
  <Column id=overall_readiness_score title="Usability score" fmt=pct0 />
  <Column id=file_recency title="File recency" />
  <Column id=published_last_updated_on title="File published" />
  <Column id=distinct_comparable_codes title="Comparable codes" fmt=num0 />
  <Column id=matched_payer_count title="Insurers matched" />
</DataTable>

<Details title="What each score component means">

- **Freshness** — how recently the hospital's file says it was updated
  (within 90 days scores 1.0, over a year scores 0.25).
- **Code coverage** — share of charge items carrying a billing code usable
  across hospitals.
- **Amount coverage** — share of price rows published as dollar amounts rather
  than percentages or formulas.
- **Insurer matching** — share of payer rates whose insurer name we could
  identify.
- **Comparison readiness** — share of rows with full service context (specific
  code, setting, and billing type).

The overall score is the simple average of the five. Full definitions and
thresholds: [scores methodology](/methodology/scores).

</Details>
