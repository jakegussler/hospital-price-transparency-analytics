# Services

Service rows are context-grained. A code can appear multiple times across
setting, billing class, modifier context, and amount kind.

```sql services
select
  service_display_label,
  service_code_key,
  '/services/' || service_code_key as service_link,
  clean_setting,
  clean_billing_class,
  modifier_display_label,
  amount_kind,
  hospital_count,
  payer_count,
  comparison_status,
  trust_band,
  variation_band,
  median_amount,
  p10_amount,
  p90_amount,
  spread_ratio_p90_to_p10
from hpt.service_market_explorer
order by
  case when comparison_status = 'insufficient_denominator' then 1 else 0 end,
  hospital_count desc,
  service_display_label
```

<DataTable data={services} link=service_link />

