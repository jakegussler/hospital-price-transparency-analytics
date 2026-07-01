# Payers

This view includes only matched payer identities from dbt. Source payer strings
that are not matched are intentionally excluded from the contracting explorer.

```sql payer_contracts
select
  payer_display_name,
  payer_type,
  market_segment,
  hospital_display_name,
  service_display_label,
  negotiated_dollar,
  hospital_cash_amount,
  payer_hospital_count,
  context_hospital_count,
  payer_match_coverage_rate,
  contract_position_band,
  cash_comparison_band
from hpt.payer_contracting_explorer
order by payer_display_name, hospital_display_name, service_display_label
limit 500
```

```sql payer_summary
select
  payer_display_name,
  count(distinct hospital_id) as hospital_count,
  count(distinct service_code_key) as service_count,
  count(*) as context_count
from hpt.payer_contracting_explorer
group by 1
order by hospital_count desc, context_count desc, payer_display_name
```

<DataTable data={payer_summary} />
<DataTable data={payer_contracts} />

