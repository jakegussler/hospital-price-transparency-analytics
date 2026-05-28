# Payer And Plan Mapping Research Prompt

Use this prompt when researching payer and plan names from hospital price
transparency negotiated-rate data and updating the dbt payer normalization seeds.

## Prompt

You are working in the Hospital Price Transparency project. Treat payer
normalization as a healthcare contracting classification problem, not as simple
string cleanup.

The goal is to create auditable payer mappings for negotiated-rate analysis
while preserving meaningful distinctions between parent organizations, payer
brands, legal entities, market segments, government programs, state Medicaid
plans, networks, and benefit lines.

Do the entity research needed to understand the payer family before editing
seeds. Do not infer all mappings from observed strings alone. For each payer
family, check online sources for separate legal entities, payer brands,
Medicare Advantage products, Medicaid managed care organizations, state-specific
plans, leased or branded networks, dental or vision benefit lines, workers'
compensation networks, and government-program contractors.

## Project Context

This repository ingests CMS hospital machine-readable files into Bronze Parquet
and uses dbt/DuckDB to normalize data into Silver. Payer normalization is handled
in the dbt transform project, primarily through these seeds:

- `transform/seeds/canonical_payers.csv`: reviewed payer, payer-program, or
  payer-network identities.
- `transform/seeds/payer_aliases.csv`: exact cleaned source payer-name mappings.
- `transform/seeds/payer_context_overrides.csv`: plan-conditioned mappings that
  refine broad payer aliases when the plan name shows a more specific segment,
  program, or network.

Relevant Silver models:

- `transform/models/silver/base/slv_base__payer_rates.sql` contains raw and
  cleaned payer and plan values.
- `transform/models/silver/core/slv_core__payer_rates.sql` applies alias and
  context mappings.
- `transform/models/silver/review_queue/slv_review_queue__payer_candidates.sql`
  summarizes mapped and unmapped payer values for review.

Do not add business normalization to Bronze parsers. This work belongs in dbt
seeds and Silver Core mapping logic.

## If You Have Database Access

Before researching, query the current data to understand all observed
configurations for the payer or payer family you are mapping. Pull payer and
plan combinations, row counts, hospital counts, state context, and current
mapping status.

Start from the review queue when available:

```sql
select *
from slv_review_queue__payer_candidates
where clean_payer_name like '%<payer token>%'
order by payer_rate_rows desc, hospital_count desc, clean_payer_name;
```

Then inspect plan context in the base payer rates:

```sql
select
    clean_payer_name,
    clean_plan_name,
    canonical_state,
    count(*) as payer_rate_rows,
    count(distinct hospital_id) as hospital_count,
    count(distinct snapshot_id) as snapshot_count,
    min(raw_payer_name) as example_raw_payer_name,
    min(raw_plan_name) as example_raw_plan_name
from slv_base__payer_rates
left join slv_base__hospital_snapshots using (snapshot_id)
where clean_payer_name like '%<payer token>%'
   or clean_plan_name like '%<payer token>%'
group by 1, 2, 3
order by payer_rate_rows desc, hospital_count desc;
```

Use the observed data to determine all possible payer plus plan configurations
currently present. Do not rely only on a short example list if the database has
more context.

## Entity Research Requirements

Before assigning canonical payer IDs, research the payer family as a real-world
healthcare organization. The research should answer:

- What parent organization owns or operates the payer brand?
- Which distinct payer entities, brands, subsidiaries, or state plans exist?
- Which Medicare Advantage, Medicaid managed care, exchange, dental, vision,
  workers' compensation, TRICARE, VA, or other government-program products exist?
- Which names are networks or product lines rather than payer identities?
- Which observed names are only plan types, age groups, service lines, provider
  categories, or hospital-specific catch-all labels?
- Which distinctions are likely to affect negotiated-rate analysis?

Search official online sources for the specific payer entity names, not just
the parent company. For example, research phrases like `Aetna Better Health of
Virginia`, `Aetna Whole Health`, `Humana Military`, `Humana ChoiceCare`, or
`UnitedHealthcare Community Plan of Tennessee` when those phrases appear in the
data.

Use online research to avoid two common errors:

- Under-mapping: collapsing distinct programs such as commercial, Medicare
  Advantage, Medicaid managed care, dental, or TRICARE into the parent payer.
- Over-mapping: creating canonical payer IDs from HMO/PPO/POS/EPO labels,
  adult/pediatric labels, service lines, or local catch-all plan text that is
  not actually a payer, product, program, or network identity.

## Mapping Principles

Separate `parent_organization` from `canonical_payer_id` and
`canonical_payer_name`. Do not collapse everything into a parent company when
product, network, government-program, or state-specific distinctions are
meaningful for negotiated-rate analysis.

For each raw payer and raw plan pattern, determine whether the value represents:

- parent company
- payer brand
- legal payer entity
- commercial product
- Medicare Advantage product
- Medicaid managed care organization
- state-specific Medicaid plan
- TRICARE, VA, or other government-program contractor
- dental, vision, behavioral health, or other benefit line
- provider or network product
- plan type such as HMO, PPO, POS, or EPO
- age category such as adult or pediatric
- service line such as transplant or behavioral health
- provider category such as PCP, specialist, or non-physician
- generic or catch-all value such as default or all other plans

Create a separate canonical payer when the value is a distinct payer, payer
program, government contractor, state Medicaid managed care plan, major market
segment, separate benefit line, or contracting network that appears meaningful
for negotiated-rate analysis.

Do not create separate canonical payers from weak generic tokens alone, such as:

- HMO, PPO, POS, EPO, ESA
- comm, mcr, mcrhmo, mcrppo, mcrpos
- adult, pediatric
- behavioral health, transplant
- PCP, specialist, non-physician
- all commercial plans, all other plans, default

Store those concepts as rationale or attributes when useful, but do not make
them payer identities unless authoritative research shows they are part of a
distinct payer, product, network, or program.

## Default Unknown Product Convention

When a cleaned payer value is only a broad parent, carrier, or brand family
name, map the identity alias to an explicit unknown-product canonical payer
rather than silently defaulting it to commercial. Use IDs such as
`aetna-unknown`, `humana-unknown`, or `<payer>-unknown` with payer category
`unknown`.

Only map a broad parent payer to a commercial, Medicare Advantage, Medicaid,
exchange, dental, workers' compensation, network, or other segment when the
payer value or plan context provides a reviewed signal for that segment. For
example, `payer = Aetna`, `plan = HMO` should stay `aetna-unknown`, while
`payer = Aetna`, `plan = Aetna Commercial Adult` can map to
`aetna-commercial`, and `payer = Aetna`, `plan = Medicare Advantage` can map to
`aetna-medicare-advantage`.

This convention should be consistent across payer families. Do not use
`<payer>` as a hidden commercial default for one family while using
`<payer>-unknown` for another unless the seed notes explain a researched,
intentional exception.

## Use Payer And Plan Context Together

Classify using both payer and plan values whenever both exist. The payer field
usually carries stronger identity context, while the plan field often carries
product, market-segment, network, or service-line context. Either field can
contain the decisive clue.

Examples:

- `payer = Aetna`, `plan = Medicare Advantage` likely maps to
  `Aetna Medicare Advantage`.
- `payer = Aetna`, `plan = Aetna Better Health of Virginia` likely maps to the
  state-specific Medicaid or dual-eligible Aetna Better Health Virginia bucket,
  subject to research.
- `payer = Humana ChoiceCare`, `plan = comm` likely maps to a ChoiceCare bucket,
  not broad Humana Commercial.
- `payer = Humana`, `plan = mcr` may map to Humana Medicare Advantage, but the
  weak token should only be used in Humana payer context and should not become a
  global payer identity rule.

## Rule Priority

Use specific mappings before generic mappings. General priority:

1. Government-program contractor or state-specific Medicaid managed care plan.
2. Distinct branded network or payer product.
3. Medicare Advantage, Medicaid, commercial, exchange, dental, vision, workers'
   compensation, or other major segment under a known payer.
4. Core payer brand.
5. Generic, unknown, or needs-review bucket.

Do not let generic tokens such as `aetna`, `humana`, `ppo`, `hmo`, `mcr`, or
`comm` override stronger phrase matches.

## Seed Update Requirements

Update the dbt seeds directly after research. Do not create a separate mapping
spreadsheet or extra research table unless the project explicitly asks for one.
The seed rows are the auditable artifact.

Add or update `transform/seeds/canonical_payers.csv` for each reviewed canonical
identity. Each canonical payer should have a stable ID, display name, parent
organization, payer category, active flag, evidence source, evidence URL when
available, and notes.

Add or update `transform/seeds/payer_aliases.csv` for exact cleaned source payer
names. Even when a payer has no alternate aliases, add an identity alias so the
clean source payer name maps to a reviewed canonical payer. For example, if the
only observed Aetna payer value is `aetna` and there is no plan context, add an
accepted alias mapping `clean_payer_name = aetna` to canonical payer
`aetna-unknown`, not to a hidden commercial default. This lets downstream
unmapped-value models distinguish reviewed identity mappings from values that
have not been worked yet.

Add or update `transform/seeds/payer_context_overrides.csv` when the plan name
refines an otherwise broad payer alias. Use context overrides for cases such as
Medicare Advantage, Medicaid, dental, TRICARE, workers' compensation, or a
reviewed network appearing under a broad payer name.

Make aliases and context overrides as general as accuracy allows. Prefer a
single confident context rule such as `plan_pattern = medicare advantage` under
`source_clean_payer_name = aetna` over many overly specific
`medicare advantage - ...` rows. Do not generalize so far that the rule creates
material false positives. Weak abbreviations such as `mcr` or `comm` should be
context-scoped to a strong payer and should usually carry lower confidence in
the notes.

Keep current seed constraints in mind:

- `payer_aliases.match_type` currently accepts `exact_clean`.
- `payer_context_overrides.match_type` accepts `exact_clean`, `plan_contains`,
  `token_contains`, and `regex`.
- `match_scope` is `global` or `state`; set `canonical_state` to a two-letter
  state for state-scoped rules and `NA` for global rules.
- `review_status` should be `accepted` only for reviewed rules that should be
  active in Silver Core joins.
- Use `source_verified` when an official source supports the mapping;
  `manual_exact`, `manual_alias`, or `inferred_from_pattern` otherwise.
- Use existing seed audit columns rather than adding a side table:
  `evidence_source`, `evidence_url`, and `notes` should capture the source type,
  source link, evidence summary, mapping rationale, confidence, and any known
  false-positive risk.
- Add seed columns only if the existing audit fields are not sufficient for a
  recurring, queryable need. If adding columns, update the CSV header, every
  seed row, and `transform/seeds/_seeds.yml` in the same change.

## Research Standard

Research official online sources before deciding that a sub-brand, network,
state-specific Medicaid plan, Medicare product, or government program should be
a separate canonical payer.

Preferred source hierarchy:

1. Official payer websites, product pages, provider manuals, and network pages.
2. CMS, TRICARE, VA, state Medicaid agency, or state insurance department pages.
3. Official provider directories or payer portals.
4. Hospital MRF context, only as supporting evidence for observed usage.
5. Secondary sources only when official sources are unavailable.

Capture source links and a short evidence summary for every recommended
canonical payer that is not obvious from the parent payer alone. Use paraphrased
evidence in seed notes; do not paste long copyrighted text into the repository.

## Confidence And Review Status

Assign confidence in seed notes:

- `high`: explicit payer, product, program, or network phrase with official
  support.
- `medium`: strong payer plus plan context, but not independently confirmed.
- `low`: weak inference from ambiguous plan or abbreviation context.
- `review`: ambiguous value or high false-positive risk.

Only accepted, active seed rows should drive production mappings. Leave risky
rules as candidates or note them for later review.

## Direct Seed Editing Checklist

When editing seeds, make the implementation itself auditable:

- Add every new canonical identity to `canonical_payers.csv` before referencing
  it from aliases or context overrides.
- Add an identity alias in `payer_aliases.csv` for each reviewed clean payer
  name, even if the alias maps the payer to itself.
- Add context overrides only when plan context should refine a broader payer
  alias.
- Prefer the broadest accurate `plan_pattern`; do not add one row per observed
  spelling when a reviewed phrase rule covers the same meaning safely.
- Put the source link in `evidence_url` when available.
- Put a compact evidence summary, confidence, and false-positive risk in
  `notes`.
- Leave ambiguous mappings inactive or with `review_status =
  needs_more_context`; do not force uncertain values into accepted mappings.

## Validation

After updating seeds, run focused dbt validation when practical:

```bash
cd transform
dbt seed --profiles-dir .
dbt run --profiles-dir . --select slv_core__payer_rates slv_review_queue__payer_candidates
dbt test --profiles-dir . --select canonical_payers payer_aliases payer_context_overrides slv_core__payer_rates slv_review_queue__payer_candidates
```

If the local DuckDB database or Bronze data is unavailable, still update the
seeds from researched evidence where possible, but explicitly state that live
data coverage was not verified.
