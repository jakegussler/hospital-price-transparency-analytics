---
title: Insurers
hide_title: true
sidebar_position: 3
---

# Insurers

Negotiated rates by insurer, across the corpus hospitals. Hospitals write
insurer names hundreds of different ways; this view includes only names we
matched to a canonical insurer identity — unmatched names never enter these
comparisons, and they stay countable on the [data quality page](/data-quality).

```sql payers
select
  payer_display_name,
  '/payers/' || canonical_payer_id as payer_link,
  payer_parent_name,
  case payer_type
    when 'national_payer' then 'National insurer'
    when 'marketplace_brand' then 'Marketplace brand'
    else replace(payer_type, '_', ' ')
  end as payer_type_label,
  hospital_count,
  service_count,
  contract_context_count,
  cash_available_context_count,
  above_cash_context_count,
  share_above_cash
from hpt.payer_overview
order by contract_context_count desc, payer_display_name
```

Click an insurer for its profile: how its negotiated rates compare to
hospitals' cash prices and to the same insurer's rates at other hospitals.

<DataTable data={payers} link=payer_link rows=25 search=true>
  <Column id=payer_display_name title="Insurer" />
  <Column id=payer_parent_name title="Parent organization" />
  <Column id=payer_type_label title="Type" />
  <Column id=hospital_count title="Hospitals" />
  <Column id=service_count title="Services" fmt=num0 />
  <Column id=contract_context_count title="Rate contexts" fmt=num0 />
  <Column id=share_above_cash title="Rates above cash price" fmt=pct0 />
</DataTable>

<SiteCallout type="definition">
"Rates above cash price" is the share of an insurer's rate contexts (where the
hospital also published a cash price) in which the negotiated rate exceeds the
hospital's own cash price. It is a signal worth examining, not proof of
overpayment — see <a href="/methodology/prices#negotiated-vs-cash">negotiated vs. cash</a>.
</SiteCallout>
