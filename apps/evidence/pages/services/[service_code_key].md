# Service {params.service_code_key}

This page shows all published contexts for the service key. The service code
alone is not the analytical grain.

```sql contexts
select
  service_display_label,
  clean_setting,
  clean_billing_class,
  modifier_display_label,
  amount_kind,
  observation_count,
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
where service_code_key = '${params.service_code_key}'
order by amount_kind, clean_setting, clean_billing_class, modifier_display_label
```

```sql hospital_rows
select
  hospital_display_name,
  amount_kind,
  clean_setting,
  clean_billing_class,
  modifier_display_label,
  hospital_amount,
  peer_hospital_count_all,
  market_median_all,
  price_position_band
from hpt.hospital_service_rankings
where service_code_key = '${params.service_code_key}'
order by service_display_label, amount_kind, hospital_display_name
```

<DataTable data={contexts} />
<DataTable data={hospital_rows} />

