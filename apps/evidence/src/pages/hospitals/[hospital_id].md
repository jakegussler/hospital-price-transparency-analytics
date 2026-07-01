# {params.hospital_id}

```sql hospital
select *
from hpt.hospital_overview
where hospital_id = '${params.hospital_id}'
```

```sql service_positions
select
  service_display_label,
  clean_setting,
  clean_billing_class,
  modifier_display_label,
  amount_kind,
  hospital_amount,
  peer_hospital_count_all,
  market_median_all,
  pct_delta_from_market_median_all,
  price_position_band
from hpt.hospital_service_rankings
where hospital_id = '${params.hospital_id}'
order by abs(coalesce(pct_delta_from_market_median_all, 0)) desc
limit 25
```

```sql payer_contexts
select
  payer_display_name,
  service_display_label,
  negotiated_dollar,
  hospital_cash_amount,
  payer_hospital_count,
  contract_position_band,
  cash_comparison_band
from hpt.payer_contracting_explorer
where hospital_id = '${params.hospital_id}'
order by payer_display_name, service_display_label
limit 50
```

```sql blocker_breakdown
select
  blocker_category,
  blocker_code,
  blocker_label,
  blocked_row_count,
  blocked_row_share
from hpt.comparison_blocker_summary
where hospital_id = '${params.hospital_id}'
order by blocked_row_count desc
```

<DataTable data={hospital} />

## Service Positions

Rows include the peer denominator and position band so rankings are interpreted
with their comparison floor.

<DataTable data={service_positions} />

## Payer Contract Context

Only matched payers appear here. Unmatched payer strings remain visible through
the blocker diagnostics, not this contracting view.

<DataTable data={payer_contexts} />

## Blocker Breakdown

<DataTable data={blocker_breakdown} />

