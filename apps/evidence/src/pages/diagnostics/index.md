# Diagnostics

The blocker vocabulary spans two BI surfaces. Row-grain blockers are listed in
the blocker summary; the denominator-floor blocker appears on service contexts
as `insufficient_denominator`.

```sql blockers
select
  hospital_display_name,
  blocker_category,
  blocker_code,
  blocker_label,
  blocked_row_count,
  classified_row_count,
  blocked_row_share
from hpt.comparison_blocker_summary
order by blocked_row_count desc
```

```sql thin_cohorts
select
  service_display_label,
  clean_setting,
  clean_billing_class,
  modifier_display_label,
  amount_kind,
  hospital_count,
  comparison_status,
  trust_band
from hpt.service_market_explorer
where comparison_status = 'insufficient_denominator'
order by hospital_count desc, service_display_label
```

<DataTable data={blockers} />

## Thin Cohorts

These rows carry the cohort-grain denominator blocker. They are visible rather
than silently removed.

<DataTable data={thin_cohorts} />

