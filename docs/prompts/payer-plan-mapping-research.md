# Payer And Plan Mapping Research Prompt

Use this prompt when researching payer and plan names from hospital price
transparency negotiated-rate data and updating the dbt payer normalization seeds.

## Prompt

You are working in the Hospital Price Transparency project. Treat payer
normalization as a healthcare contracting classification problem, not as simple
string cleanup.

The goal is to create auditable payer mappings for negotiated-rate analysis
while keeping payer identity separate from plan, product, program, network,
market-segment, and benefit-line context.

Do not encode every product or program distinction into `canonical_payer_id`.
`canonical_payer_id` should answer "who is the payer, payer brand, administrator,
network, or BCBS licensee?" Context columns should answer "what kind of plan,
product, program, network, benefit line, or state context is this?"

## Project Context

This repository ingests CMS hospital machine-readable files into Bronze Parquet
and uses dbt/DuckDB to normalize data into Silver. Payer normalization is handled
in the dbt transform project, primarily through these seeds:

- `transform/seeds/canonical_payers.csv`: broad reviewed payer identities.
- `transform/seeds/payer_aliases.csv`: exact cleaned source payer-name mappings
  to broad canonical payer identities.
- `transform/seeds/payer_context_rules.csv`: payer/plan context rules that
  enrich rows with market, program, product, network, benefit-line, funding, and
  state context without replacing `canonical_payer_id`.

Relevant Silver models:

- `transform/models/silver/base/slv_base__payer_rates.sql` contains raw and
  cleaned payer and plan values.
- `transform/models/silver/core/slv_core__payer_alias_matches.sql` resolves
  broad payer identity from `payer_aliases`.
- `transform/models/silver/core/slv_core__payer_context_matches.sql` applies
  context enrichment rules after identity matching.
- `transform/models/silver/core/slv_core__payer_rates.sql` exposes broad payer
  identity plus separate context columns.
- `transform/models/silver/review_queue/slv_review_queue__payer_candidates.sql`
  summarizes unmatched payer values where no broad canonical payer identity was
  found.
- `transform/models/silver/review_queue/slv_review_queue__payer_plan_candidates.sql`
  summarizes unmatched payer plus plan combinations so reviewers can see the
  plan context attached to unmapped payers.

Do not add business normalization to Bronze parsers. This work belongs in dbt
seeds and Silver Core mapping logic.

## If You Have Database Access

Before researching, query the current data to understand which unmatched payer
values matter most and what plan context appears with them. Pull row counts,
hospital counts, snapshot counts, source-format counts, example states, state
counts, example raw values, and distinct plan counts from the review queues.

Start with unmatched payer names. This is the best queue for deciding which
`payer_aliases.csv` rows or new broad `canonical_payers.csv` rows are needed:

```sql
select *
from slv_review_queue__payer_candidates
where clean_payer_name like '%<payer token>%'
   or example_clean_plan_name like '%<payer token>%'
order by payer_rate_rows desc, hospital_count desc, clean_payer_name;
```

Then inspect unmatched payer plus plan combinations. This is the best queue for
finding plan names that may justify context rules after the payer identity is
mapped:

```sql
select *
from slv_review_queue__payer_plan_candidates
where clean_payer_name like '%<payer token>%'
   or clean_plan_name like '%<payer token>%'
order by payer_rate_rows desc, hospital_count desc, clean_payer_name, clean_plan_name;
```

Use `slv_review_queue__payer_candidates` to prioritize unmapped payer identity
work. Use `slv_review_queue__payer_plan_candidates` to understand the plans
associated with those unmapped payers and to identify likely
`payer_context_rules.csv` additions. Both review queues intentionally expose
`example_state` and `state_count`; do not treat state as part of the grouping
unless a specific state-scoped rule or BCBS licensee decision requires it.

Only drill into base payer rates after the review queues show a candidate that
needs deeper inspection:

```sql
select
    pr.clean_payer_name,
    pr.clean_plan_name,
    snapshots.canonical_state,
    count(*) as payer_rate_rows,
    count(distinct pr.hospital_id) as hospital_count,
    count(distinct pr.snapshot_id) as snapshot_count,
    min(pr.raw_payer_name) as example_raw_payer_name,
    min(pr.raw_plan_name) as example_raw_plan_name
from slv_base__payer_rates pr
left join slv_base__hospital_snapshots snapshots
    on pr.snapshot_id = snapshots.snapshot_id
where pr.clean_payer_name like '%<payer token>%'
   or pr.clean_plan_name like '%<payer token>%'
group by 1, 2, 3
order by payer_rate_rows desc, hospital_count desc;
```

Use the observed data to determine all possible payer plus plan configurations
currently present. Do not rely only on a short example list if the database has
more context.

## Entity Research Requirements

Before assigning or changing mappings, research the payer family as a real-world
healthcare organization. The research should answer:

- What parent organization owns or operates the payer brand?
- Which distinct payer brands, administrators, networks, subsidiaries, legal
  entities, or BCBS licensees exist?
- Which Medicare Advantage, Medicaid managed care, exchange, dental, vision,
  workers' compensation, TRICARE, VA, or other government-program products exist?
- Which names are networks, products, programs, or benefit lines rather than
  payer identities?
- Which observed names are only plan types, age groups, service lines, provider
  categories, or hospital-specific catch-all labels?
- Which distinctions are useful for negotiated-rate analysis as context, without
  needing their own canonical payer ID?

Search official online sources for the specific payer entity names, not just the
parent company. For example, research phrases like `Aetna Better Health of
Virginia`, `Aetna Whole Health`, `Humana Military`, `Humana ChoiceCare`, or
`UnitedHealthcare Community Plan of Tennessee` when those phrases appear in the
data. The result should usually be a broad payer identity plus context fields,
not a new product-specific canonical payer.

Use online research to avoid two common errors:

- Under-mapping: collapsing distinct payer brands, administrators, BCBS licensees,
  or dental/behavioral payers into a parent company.
- Over-mapping: creating canonical payer IDs from Medicare, Medicaid, commercial,
  HMO/PPO/POS/EPO, network, state-program, service-line, or local catch-all plan
  text that should be context.

## Mapping Principles

Separate these concepts:

- `canonical_payer_id`: broad payer, payer brand, administrator, network, or
  BCBS licensee used for business comparison.
- `payer_parent_id` / `payer_parent_name`: corporate parent rollup, when useful.
- `market_segment`: financing or coverage market, such as commercial, Medicare
  Advantage, Medicaid managed care, exchange, workers comp, TRICARE/VA, or
  unknown.
- `program_type`: specific program context such as D-SNP, TennCare, Medi-Cal,
  Federal Employee Program, or VA CCN.
- `product_or_network_name`: named product or network such as Aetna Whole Health,
  Aetna VHAN, UHC Choice Plus, UHC West, BlueAdvantage, BlueCare Plus, or Humana
  ChoiceCare.
- `subsidiary_or_brand`: operating brand or subsidiary such as Aetna Better
  Health, UnitedHealthcare Community Plan, Humana Military, Optum, or BlueCare
  Tennessee.
- `benefit_line`: medical, dental, vision, behavioral health, transplant, or
  unknown.
- `plan_type`: HMO, PPO, POS, EPO, PFFS, and similar plan-type labels.
- `context_state`: state implied by a product or program, especially Medicaid
  managed care context.

Do not collapse everything to parent organizations. Aetna should remain
`canonical_payer_id = aetna` with parent `cvs_health`; UnitedHealthcare should
remain `canonical_payer_id = unitedhealthcare` with parent
`unitedhealth_group`. UMR, Surest, Optum, PHCS, First Health, and dental-only
payers may remain separate canonical identities when they are presented as
distinct payers, administrators, or networks.

Do not create separate canonical payers from weak generic tokens alone, such as:

- HMO, PPO, POS, EPO, ESA, PFFS
- comm, mcr, mcrhmo, mcrppo, mcrpos
- adult, pediatric
- behavioral health, transplant
- PCP, specialist, non-physician
- all commercial plans, all other plans, default

Store those concepts as context fields when useful, but do not make them payer
identities.

## Canonical Payer Identity Rules

Create or update `canonical_payers.csv` only for broad payer identities that
should be useful in payer-level analysis. Examples:

- `aetna`
- `unitedhealthcare`
- `humana`
- `cigna`
- `caresource`
- `molina`
- `wellcare`
- `wellpoint`
- `umr`
- `surest`
- `optum`
- `bcbs_tennessee`
- `bcbs_michigan`
- `anthem_blue_cross_california`
- `blue_shield_california`

Do not add product-specific canonical IDs such as:

- `aetna-commercial`
- `aetna-medicare-advantage`
- `aetna-better-health-virginia`
- `united-healthcare-community-plan-tennessee`
- `united-healthcare-dental`
- `humana-choicecare`
- `humana-medicare-advantage`
- `wellcare-tennessee`

Those distinctions belong in `payer_context_rules.csv`.

## Unknown Context Convention

When a cleaned payer value is only a broad carrier or brand name, map the alias
to the broad canonical payer ID and leave product/program context unknown unless
the payer value or plan context provides a reviewed signal.

Examples:

- `payer = Aetna`, no useful plan context: `canonical_payer_id = aetna`,
  `market_segment = unknown`.
- `payer = Aetna`, `plan = HMO`: `canonical_payer_id = aetna`,
  `market_segment = unknown`; HMO alone is not enough to infer commercial.
- `payer = Aetna`, `plan = Aetna Commercial Adult`:
  `canonical_payer_id = aetna`, `market_segment = commercial`.
- `payer = Aetna`, `plan = Medicare Advantage`:
  `canonical_payer_id = aetna`, `market_segment = medicare_advantage`,
  `program_type = medicare_advantage`.

Do not use `<payer>-unknown` canonical IDs. Unknown product context is represented
by context/default fields, not by payer identity.

## Use Payer And Plan Context Together

Classify using both payer and plan values whenever both exist. The payer field
usually carries stronger identity context, while the plan field often carries
product, market-segment, network, program, or service-line context. Either field
can contain the decisive clue.

Examples:

- `payer = Aetna`, `plan = Medicare Advantage` should map to
  `canonical_payer_id = aetna`, `market_segment = medicare_advantage`.
- `payer = Aetna`, `plan = Aetna Better Health of Virginia` should map to
  `canonical_payer_id = aetna`, with Medicaid/Medicare, Better Health, and
  Virginia context depending on researched plan text.
- `payer = Humana ChoiceCare`, `plan = comm` should map to
  `canonical_payer_id = humana`, `product_or_network_name = humana_choicecare`.
- `payer = Humana`, `plan = mcr` may classify Medicare Advantage context, but
  the weak token should only be used in Humana payer context.
- `payer = UMR`, `plan = UHC network text` should stay
  `canonical_payer_id = umr`; UHC network access is context, not identity
  override.

## Rule Priority

Use specific context rules before generic rules. General priority:

1. Explicit D-SNP, VA CCN, TRICARE, or state Medicaid program signals.
2. Distinct branded network or product signals.
3. Medicare Advantage, Medicaid, commercial, exchange, dental, vision, workers
   comp, or other major segment under a known payer.
4. Payer-name-only context from an alias that itself includes product/program
   words, such as `Humana Dental` or `Wellcare Medicare`.
5. Generic unknown or needs-review context.

Use `payer_context_rules.priority`; lower numbers win. Do not let generic tokens
such as `aetna`, `humana`, `ppo`, `hmo`, `mcr`, `comm`, or broad commercial
phrases override stronger phrase matches.

## Seed Update Requirements

Update the dbt seeds directly after research. Do not create a separate mapping
spreadsheet or extra research table unless the project explicitly asks for one.
The seed rows are the auditable artifact.

Add or update `transform/seeds/canonical_payers.csv` only for broad reviewed
identities. Columns are:

```text
canonical_payer_id, canonical_payer_name, payer_parent_id, payer_parent_name,
payer_type, default_market_segment, default_benefit_line, active,
evidence_source, evidence_url, notes
```

Add or update `transform/seeds/payer_aliases.csv` for exact cleaned source payer
names. Even when a payer has no alternate aliases, add an identity alias so the
clean source payer name maps to a reviewed broad canonical payer. For example,
`clean_payer_name = aetna` should map to `canonical_payer_id = aetna`, not to a
product or unknown-product ID.

Add or update `transform/seeds/payer_context_rules.csv` when the payer name or
plan name supplies product, market-segment, program, network, benefit-line,
funding, or state context. Context rules enrich rows; they do not replace
`canonical_payer_id`.

Make aliases and context rules as general as accuracy allows. Prefer a single
confident rule such as `plan_pattern = medicare advantage` under
`source_canonical_payer_id = aetna` over many overly specific
`medicare advantage - ...` rows. Do not generalize so far that the rule creates
material false positives. Weak abbreviations such as `mcr` or `comm` should be
context-scoped to a strong payer and should usually carry lower confidence in
the notes.

Keep current seed constraints in mind:

- `payer_aliases.match_type` currently accepts `exact_clean`.
- `payer_context_rules.match_type` accepts `payer_name`, `exact_clean`,
  `plan_contains`, `token_contains`, and `regex`.
- `match_scope` is `global` or `state`; set `match_state` to a two-letter state
  for state-scoped context rules and blank for global rules.
- `source_canonical_payer_id` should usually be populated and should reference
  an active row in `canonical_payers.csv`.
- `source_clean_payer_name` is optional but useful when a context rule should
  apply only to one exact payer alias under a broader canonical payer.
- `review_status` should be `accepted` only for reviewed rules that should be
  active in Silver Core joins.
- Use `source_verified` when an official source supports the mapping;
  `manual_exact`, `manual_alias`, or `inferred_from_pattern` otherwise.
- Use existing audit columns rather than adding a side table:
  `evidence_source`, `evidence_url`, and `notes` should capture the source type,
  source link, evidence summary, mapping rationale, confidence, and any known
  false-positive risk.
- Add seed columns only if the existing audit fields are not sufficient for a
  recurring, queryable need. If adding columns, update the CSV header, every seed
  row, and `transform/seeds/_seeds.yml` in the same change.

## Research Standard

Research official online sources before deciding that a sub-brand, network,
state-specific Medicaid plan, Medicare product, or government program should be
classified.

Preferred source hierarchy:

1. Official payer websites, product pages, provider manuals, and network pages.
2. CMS, TRICARE, VA, state Medicaid agency, or state insurance department pages.
3. Official provider directories or payer portals.
4. Hospital MRF context, only as supporting evidence for observed usage.
5. Secondary sources only when official sources are unavailable.

Capture source links and a short evidence summary for every recommended
canonical payer or context rule that is not obvious from the payer name alone.
Use paraphrased evidence in seed notes; do not paste long copyrighted text into
the repository.

## Confidence And Review Status

Use `payer_context_rules.context_confidence`:

- `high`: explicit payer, product, program, or network phrase with official
  support.
- `medium`: strong payer plus plan context, but not independently confirmed.
- `low`: weak inference from ambiguous plan or abbreviation context.

Only accepted, active seed rows should drive production mappings. Leave risky
rules as candidates or note them for later review.

## Direct Seed Editing Checklist

When editing seeds, make the implementation itself auditable:

- Add every new broad canonical identity to `canonical_payers.csv` before
  referencing it from aliases or context rules.
- Add an identity alias in `payer_aliases.csv` for each reviewed clean payer
  name, even if the alias maps the payer to itself.
- Add context rules only when payer or plan context should enrich a broader
  payer identity.
- Prefer the broadest accurate `plan_pattern`; do not add one row per observed
  spelling when a reviewed phrase rule covers the same meaning safely.
- Use `priority` to make specific rules beat generic rules.
- Put the source link in `evidence_url` when available.
- Put a compact evidence summary, confidence, and false-positive risk in
  `notes`.
- Leave ambiguous mappings inactive or with `review_status =
  needs_more_context`; do not force uncertain values into accepted mappings.

## Validation

After updating seeds, run focused dbt validation when practical:

```bash
cd transform
dbt seed --full-refresh --profiles-dir . --select canonical_payers payer_aliases payer_context_rules
dbt build --profiles-dir . --select canonical_payers payer_aliases payer_context_rules silver.core silver.review_queue
```

If the local DuckDB database or Bronze data is unavailable, still update the
seeds from researched evidence where possible, but explicitly state that live
data coverage was not verified.
