# Hospitals

Hospital readiness scores describe the usability of published data for this
project's comparison framework. They are not legal compliance findings.

```sql hospitals
select
  hospital_display_name,
  hospital_id,
  '/hospitals/' || hospital_id as hospital_link,
  health_system,
  hospital_type,
  overall_readiness_score,
  comparison_readiness_score,
  payer_mapping_score,
  trust_band,
  freshness_bucket,
  benchmark_context_count,
  benchmark_services_meeting_floor,
  payer_contract_context_count,
  matched_payer_count,
  snapshot_id
from hpt.hospital_overview
order by overall_readiness_rank, hospital_display_name
```

<DataTable data={hospitals} link=hospital_link />

