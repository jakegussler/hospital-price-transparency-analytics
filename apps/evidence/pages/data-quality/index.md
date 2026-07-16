---
title: Data Quality
hide_title: true
sidebar_position: 4
---

# Data Quality: How Much Is Actually Comparable?

Hospital price files contain many rows that cannot support a fair
cross-hospital comparison. This page counts how many rows pass each comparison
rule and reports why other rows are excluded from rankings.

<SiteCallout type="definition">
"Blocked" never means hidden. Every published row stays visible somewhere on
this site; blocking only controls whether a row is allowed into cross-hospital
rankings and market statistics.
</SiteCallout>

## The comparability funnel

```sql corpus_funnel
select
  stage_index,
  stage_index::int || '. ' || stage_label as stage,
  row_count,
  share_of_published
from hpt.comparability_funnel
where scope_level = 'corpus'
order by stage_index
```

<BarChart
  data={corpus_funnel}
  x=stage
  y=row_count
  swapXY=true
  sort=false
  yFmt=num0
  title="Price rows surviving each comparison rule (all hospitals)"
/>

<DataTable data={corpus_funnel}>
  <Column id=stage title="Stage" />
  <Column id=row_count title="Price rows" fmt=num0 />
  <Column id=share_of_published title="Share of published" fmt=pct1 />
</DataTable>

The five stages, in plain language:

1. **Published** — every price row we classified from the hospitals' current
   files.
2. **Code usable across hospitals** — the row carries a billing code from a
   standard code system (MS-DRG, CPT, HCPCS, …), not an internal chargemaster
   code only one hospital understands.
3. **Full service context** — the code is specific and the row says which care
   setting and billing type it covers, so we know we are comparing the same
   economic thing.
4. **Rankable dollar price** — the row is an actual dollar amount, not a
   percentage, formula, or estimate.
5. **Meets the 3-hospital floor** — at least 3 hospitals report the exact same
   context, our minimum for any market statistic.

## Blocked rows by hospital

A single row can carry several blockers at once, so counts overlap across
reasons.

```sql hospital_blockers
select
  hospital_display_name,
  case blocker_category
    when 'snapshot_freshness' then 'Outdated file version'
    when 'code_comparability' then 'Billing code not comparable'
    when 'amount_semantics' then 'Not a rankable dollar price'
    when 'service_context' then 'Service context must stay separate'
    when 'payer_identity' then 'Insurer name not identified'
    when 'payer_context' then 'Insurance market type unknown'
  end as blocker_group,
  sum(blocked_row_count) as blocked_row_count
from hpt.comparison_blocker_summary
group by hospital_display_name, blocker_category
order by hospital_display_name, blocked_row_count desc
```

<BarChart
  data={hospital_blockers}
  x=hospital_display_name
  y=blocked_row_count
  series=blocker_group
  yFmt=num0
  title="Blocked rows by hospital and reason group (overlapping counts)"
/>

```sql blocker_detail
select
  hospital_display_name,
  blocker_label,
  blocker_code,
  blocked_row_count,
  classified_row_count,
  blocked_row_share
from hpt.comparison_blocker_summary
order by blocked_row_count desc
```

<DataTable data={blocker_detail} rows=25 search=true>
  <Column id=hospital_display_name title="Hospital" />
  <Column id=blocker_label title="Reason" />
  <Column id=blocker_code title="Code" />
  <Column id=blocked_row_count title="Rows" fmt=num0 />
  <Column id=blocked_row_share title="Share of rows" fmt=pct1 />
</DataTable>

## Every blocker, explained

The comparison framework names 12 blockers. Ten apply to individual rows; the
other two are properties of a whole service context or insurer contract, so
they appear as the "Too few hospitals" status and the excluded-contract counts
on service pages rather than in the table above. For each blocker we also say
**whose limitation it is** — the hospital's file, our framework's strictness,
or this project's current coverage.

**Row-level blockers:**

- **From an outdated file version** (`not_current_snapshot`) — the row came
  from a superseded file. *Framework rule:* only current files enter
  comparisons.
- **Billing code can't be matched across hospitals**
  (`code_not_cross_hospital_comparable`) — internal chargemaster or local
  codes mean something only inside one hospital. *Hospital's file.*
- **Code too general to identify one service** (`code_not_specific`) — e.g. a
  broad revenue-center code covering many different services. *Hospital's
  file, applied by a framework rule.*
- **No usable billing code** (`missing_match_code`) — the row has no
  normalized code at all. *Hospital's file.*
- **Not a dollar price** (`non_rankable_amount`) — the "price" is a
  percentage of charges, an algorithm description, or an estimate. Visible as
  context, never ranked. *Hospital's file, protected by a framework rule.*
- **Dollar value calculated, not directly quoted** (`derived_dollar`) — a
  dollar figure derived from a percentage or formula. We refuse to rank it
  against directly quoted prices. *Framework strictness.*
- **Modifier changes what's being priced** (`modifier_context_required`) —
  billing modifiers (like professional-only or technical-only components)
  change the economic object; such rows are compared only against identical
  modifier contexts. *Framework strictness.*
- **Drug price without dose/unit information** (`drug_unit_context_missing`)
  — a drug price without units cannot be compared per-dose. *Hospital's
  file.*
- **Insurer name couldn't be identified** (`payer_unmatched`) — we could not
  confidently match the published payer string to a canonical insurer. The row
  is excluded from insurer views but counted here. *This project's current
  matching coverage.*
- **Insurance market type unknown** (`market_segment_unknown`) — the row does
  not say whether it covers commercial, Medicare Advantage, etc. It is
  excluded only from market-segment cuts. *Hospital's file.*

**Context-level blockers:**

- **Too few hospitals** (`below_min_hospital_denominator`) — fewer than 3
  hospitals have a safely representable price for the exact service context.
  The context stays fully visible with its individual prices, but no median,
  percentile, or ranking is computed. *Framework rule protecting against
  false precision.*
- **Contract has mixed amounts** (`multiple_amounts_per_contract_context`) —
  one insurer contract carries several different dollar amounts for the exact
  same service context, usually a hidden distinction (a revenue-code or
  network difference) the published file does not label. We refuse to average
  those into one number: the contract's rows stay visible and downloadable,
  but the contract is excluded from every statistic, and service pages show
  how many hospitals were excluded this way. *Hospital's file, protected by a
  framework rule.*

**Statistics are hospital-weighted.** Every market median and percentile is
computed over ONE representative price per hospital — a rate repeated across
dozens of rows (for example one per-diem published against 56 revenue-code
variants) counts exactly once, and negotiated methodologies (fee schedule /
case rate / per diem) are never mixed in one distribution.

## Thin contexts (below the 3-hospital floor)

```sql thin_summary
select
  count(*) as thin_context_count,
  (select count(*) from hpt.service_market_explorer) as total_context_count
from hpt.service_market_explorer
where comparison_status = 'insufficient_denominator'
```

 {(thin_summary[0]?.thin_context_count ?? 0).toLocaleString()} of {(thin_summary[0]?.total_context_count ?? 0).toLocaleString()} published service contexts are currently below the floor. They are labeled, never
silently dropped. The largest ones by published volume:

```sql thin_contexts
select
  service_display_label,
  '/compare/' || service_url_slug as service_link,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type,
  case clean_setting
    when 'unspecified' then 'Not specified'
    else clean_setting
  end as setting,
  hospital_count,
  observation_count
from hpt.service_market_explorer
where comparison_status = 'insufficient_denominator'
order by observation_count desc, service_display_label
limit 100
```

Showing the top {thin_contexts.length} thin contexts by row volume.

<DataTable data={thin_contexts} link=service_link rows=25>
  <Column id=service_display_label title="Service" />
  <Column id=price_type title="Price type" />
  <Column id=setting title="Care setting" />
  <Column id=hospital_count title="Hospitals (n)" />
  <Column id=observation_count title="Price rows" fmt=num0 />
</DataTable>

<SiteCallout type="scope">
A context clears the floor only when at least three hospitals publish the same
code, setting, billing type, modifiers, and price type. Adding hospitals can
increase the number of qualifying contexts without changing the methodology.
</SiteCallout>
