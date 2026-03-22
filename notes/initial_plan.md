# Hospital Price Transparency Pipeline — Initial Plan

## Recommended Project Scope

Do not start with "all hospitals." Start with a constrained but analytically useful slice.

**Use this initial scope:**
- 15–25 hospitals
- 3–5 health systems
- 3 regions
- A mix of:
  - Academic medical centers
  - Community hospitals
  - For-profit hospitals
  - Nonprofit hospitals

That is large enough to show real variation, but small enough that you can actually finish.

**A good MVP would be:**
- Tennessee
- North Carolina
- Florida

Or: one large national system plus several independents.

The point is to have meaningful variation in geography and ownership.

---

## What Questions Your Gold Layer Should Answer

You already listed the right ones. Formalize them into metric families.

### 1. Negotiated-Rate Spread for the Same Service

For a given normalized service, compare the distribution of payer-specific negotiated rates within each hospital.

**Example gold metrics:**
- `min_negotiated_rate`
- `max_negotiated_rate`
- `median_negotiated_rate`
- `spread_amount` = max - min
- `spread_ratio` = max / min
- `coefficient_of_variation`
- `count_of_distinct_payer_plan_rates`

> Supports: "which hospitals have the widest negotiated-rate spread for the same service?"

### 2. Cash vs. Negotiated Commercial Rates

For the same normalized service at a hospital:
- `discounted_cash_price`
- `median_negotiated_commercial_rate`
- `min_negotiated_commercial_rate`
- `max_negotiated_commercial_rate`
- `cash_to_median_negotiated_ratio`
- `cash_cheaper_than_negotiated_flag`

> Supports: "how do cash prices compare to negotiated commercial rates?"

### 3. Compliance / Standardization Quality

Distinguish two concepts:
- **Regulatory compliance signals**
- **Data standardization quality**

These are related but not identical.

**Possible compliance/quality metrics:**
- `public_file_accessible`
- `file_parseable`
- `required_fields_present`
- `npi_present`
- `payer_names_present`
- `code_type_code_present`
- `rows_missing_numeric_price` (count)
- `pct_rows_unhelpful_descriptions`
- `pct_payer_names_requiring_normalization`
- `file_last_updated` / `stale_flag`
- `adherence_to_expected_mrf_structures`
- `allowed_amount_fields_present` (2026 requirements)

> CMS has also published enforcement activity data and notices, which gives you an external benchmark you can optionally join later.

### 4. Regional / Hospital-Type Variation

**Aggregate by:**
- State
- Hospital referral region or metro area
- Rural vs. urban
- Teaching vs. non-teaching
- Ownership type
- System affiliation

**Compare:**
- Median rates by service
- Dispersion by service
- Cash discount prevalence
- Standardization quality score

---

## The Data Architecture

Use a standard bronze / silver / gold pattern.

### Bronze: Preserve the Source Exactly

**Purpose:** Reproducibility and auditability.

**Store:**
- Raw downloaded file
- Source URL
- Download timestamp
- Content hash
- HTTP metadata
- Parsed raw row JSON
- Hospital identifier
- Source file format
- Extraction run ID

You want **two** bronze tables, not one:

#### `bronze_hospital_source_files`
One row per source file.

| Column | Notes |
|---|---|
| `source_file_id` | |
| `hospital_id` | |
| `source_url` | |
| `source_filename` | |
| `file_format` | |
| `downloaded_at` | |
| `content_hash` | |
| `http_status` | |
| `file_size_bytes` | |
| `published_date_if_available` | |
| `raw_storage_path` | |

#### `bronze_hospital_price_rows`
One row per extracted raw row from the file.

| Column | Notes |
|---|---|
| `bronze_row_id` | |
| `source_file_id` | |
| `raw_row_json` | |
| `raw_row_number` | |
| `extracted_at` | |

> Why? Because hospitals publish wildly different JSON, CSV, XLSX, or zipped outputs. You need file-level metadata separate from row-level extracted content.

---

### Silver: Standardized Entities

This is where the real work is.

#### `silver_hospitals`
Normalized hospital metadata.

| Column | Notes |
|---|---|
| `hospital_id` | |
| `hospital_name` | |
| `system_name` | |
| `state` | |
| `city` | |
| `zip` | |
| `ownership_type` | |
| `hospital_type` | |
| `teaching_flag` | |
| `rural_urban_flag` | |
| `bed_count` | if you can source it |
| `type_2_npi` | |
| `cms_certification_number` | if available |

#### `silver_services`
Normalized service catalog.

| Column | Notes |
|---|---|
| `service_id` | |
| `raw_service_description` | |
| `normalized_service_name` | |
| `service_category` | |
| `code_type` | |
| `billing_code` | |
| `code_modifier` | |
| `setting` | |
| `revenue_code` | if present |
| `ms_drg` | if present |
| `hcpcs_cpt` | if present |

#### `silver_payers`
Normalized payer and plan names.

| Column | Notes |
|---|---|
| `payer_id` | |
| `raw_payer_name` | |
| `normalized_payer_name` | |
| `raw_plan_name` | |
| `normalized_plan_name` | |
| `payer_group` | |
| `market_type` | |

#### `silver_standard_charges`
The core fact-like table at the row level.

**Grain:** one hospital + one service + one payer/plan + one charge type + one source row

| Column | Notes |
|---|---|
| `standard_charge_id` | |
| `hospital_id` | |
| `service_id` | |
| `payer_id` | nullable for de-identified or cash rows |
| `source_file_id` | |
| `charge_type` | |
| `negotiated_arrangement_type` | |
| `negotiated_rate_numeric` | |
| `negotiated_rate_text` | |
| `gross_charge` | |
| `discounted_cash_price` | |
| `deidentified_min_rate` | |
| `deidentified_max_rate` | |
| `allowed_amount_median` | |
| `allowed_amount_p10` | |
| `allowed_amount_p90` | |
| `allowed_amount_count` | |
| `currency_code` | |
| `inpatient_outpatient_setting` | |
| `row_quality_status` | |
| `parse_notes` | |
| `effective_date` | if available |
| `last_updated_date` | if available |

#### `silver_compliance_observations`
**Grain:** one hospital + one file version + one rule/check

| Column |
|---|
| `hospital_id` |
| `source_file_id` |
| `check_name` |
| `check_status` |
| `severity` |
| `observed_value` |
| `notes` |

> This table is extremely useful. It powers your compliance dashboards without mixing those checks into the pricing fact table.

---

### Gold: Analytics Marts

Build marts around business questions.

#### `gold_service_price_summary`
**Grain:** one hospital + one normalized service

**Measures:**
- `distinct_payers`
- `min_negotiated_rate`
- `max_negotiated_rate`
- `median_negotiated_rate`
- `avg_negotiated_rate`
- `negotiated_spread_amount`
- `negotiated_spread_ratio`
- `cash_price`
- `cash_vs_median_ratio`
- `deidentified_min_rate`
- `deidentified_max_rate`
- `row_count_used`

#### `gold_hospital_compliance_scorecard`
**Grain:** one hospital + snapshot date

**Measures:**
- `file_accessible_flag`
- `parse_success_flag`
- `required_field_completeness_pct`
- `payer_name_standardization_pct`
- `coded_service_pct`
- `numeric_price_pct`
- `allowed_amount_fields_present_flag`
- `overall_standardization_score`
- `overall_compliance_signal_score`

#### `gold_region_service_variation`
**Grain:** one region + one normalized service

**Measures:**
- `hospitals_reporting_count`
- `median_of_hospital_medians`
- `p25_hospital_median`
- `p75_hospital_median`
- `regional_variation_ratio`
- `avg_cash_vs_negotiated_ratio`

---

## The Hardest Technical Problem: Service Normalization

This is the part that can make or break the project.

Hospitals will not publish services consistently. The same service may appear as:
- `MRI BRAIN W/O CONTRAST`
- `MRI Brain without Contrast`
- `Magnetic Resonance Imaging, Brain, No Contrast`
- `CPT 70551`

### Best Approach for MVP

Use a layered matching strategy:

**Tier 1: Exact billing code match**
If CPT/HCPCS/MS-DRG/revenue code exists, use that as the primary anchor.

**Tier 2: Deterministic text normalization**
Normalize description text with rules:
- Uppercase
- Strip punctuation
- Normalize abbreviations
- Standardize "W/O" → "WITHOUT"
- Remove vendor noise

**Tier 3: Mapping table**
Maintain a manually curated `service_normalization_map`:

| Column |
|---|
| `raw_code_type` |
| `raw_code` |
| `raw_description_pattern` |
| `normalized_service_name` |
| `service_category` |
| `confidence_level` |

**Tier 4: Fallback fuzzy matching**
Only for unmatched rows. Do not make fuzzy matching your primary production logic.

> This is one of the best parts of the project for interviews because it shows pragmatic thinking: first use codes, then deterministic rules, then curated mappings, then fuzzy fallback.

---

## The Second Hardest Problem: Payer Normalization

Payer names will be messy. Examples:
- `BLUE CROSS BLUE SHIELD`
- `BCBS`
- `BlueCross BlueShield of TN`
- `BCBS TN PPO`

Separate these concepts:
- Payer name
- Plan name
- Payer group

Use a mapping table — `payer_normalization_map`:

| Column |
|---|
| `raw_payer_name` |
| `raw_plan_name` |
| `normalized_payer_name` |
| `normalized_plan_name` |
| `payer_group` |
| `market_type` |
| `confidence` |

> You do not need perfect payer normalization for MVP. You need good enough grouping for major commercial comparisons.

---

## Incremental Loading Strategy

Do not overcomplicate incremental logic initially. Since hospital price files can be republished in full, the safest design is **file-level incremental**:

Each Airflow run:
1. Request source URL
2. Compare content hash or last-modified metadata
3. If unchanged → skip downstream parsing
4. If changed → ingest new file version and process

That means your incrementality is based on **source file versioning**, not row-level CDC. This is the correct approach for this domain.

**Practical pattern** — for each hospital:
1. Track source URL
2. Store previous content hash
3. If hash changed → create new `source_file_id`
4. Parse all rows from the new version
5. Rebuild dependent silver facts for that file version
6. Refresh gold marts

This is easier and more defensible than trying to infer row-level deltas in messy semi-structured files.

---

## Airflow Design

Use Airflow for orchestration, but keep business logic outside DAG files. Your DAG should orchestrate tasks, not contain transformation logic.

### DAG: `hospital_price_transparency_pipeline`

**Tasks:**
1. `get_active_hospital_targets`
2. `check_source_file_metadata`
3. `download_changed_files`
4. `extract_raw_rows`
5. `load_bronze_source_files`
6. `load_bronze_price_rows`
7. `transform_silver_hospitals`
8. `transform_silver_services`
9. `transform_silver_payers`
10. `transform_silver_standard_charges`
11. `run_compliance_checks`
12. `build_gold_service_price_summary`
13. `build_gold_hospital_compliance_scorecard`
14. `build_gold_region_service_variation`
15. `run_data_quality_tests`
16. `notify_summary`

### Repository Structure

```
hospital-price-transparency/
├─ airflow/
│  ├─ dags/
│  │  └─ hospital_price_pipeline.py
│  ├─ plugins/
│  └─ requirements.txt
├─ app/
│  ├─ extract/
│  │  ├─ discover.py
│  │  ├─ download.py
│  │  ├─ parse_json.py
│  │  ├─ parse_csv.py
│  │  ├─ parse_xlsx.py
│  │  └─ file_router.py
│  ├─ transform/
│  │  ├─ bronze_loader.py
│  │  ├─ silver_hospitals.py
│  │  ├─ silver_services.py
│  │  ├─ silver_payers.py
│  │  ├─ silver_standard_charges.py
│  │  ├─ compliance_checks.py
│  │  └─ gold_marts.py
│  ├─ db/
│  │  ├─ models/
│  │  ├─ ddl/
│  │  └─ connection.py
│  ├─ mappings/
│  │  ├─ payer_normalization.csv
│  │  └─ service_normalization.csv
│  └─ utils/
│     ├─ logging.py
│     ├─ hashing.py
│     └─ config.py
├─ sql/
│  ├─ bronze/
│  ├─ silver/
│  ├─ gold/
│  └─ tests/
├─ terraform/
│  ├─ modules/
│  ├─ dev/
│  └─ variables.tf
├─ docker/
│  ├─ Dockerfile.app
│  ├─ Dockerfile.airflow
│  └─ init/
├─ dashboards/
│  ├─ metabase/
│  └─ superset/
├─ data/
│  └─ sample_files/
├─ docker-compose.yml
└─ README.md
```

That structure clearly separates orchestration, app code, SQL, infra, and BI.

### What Code Goes Where

| Layer | Use |
|---|---|
| **Python** | File download, raw parsing, file format routing, text cleanup helpers, mapping application |
| **SQL** | Bronze-to-silver relational transformations, deduplication, aggregations, gold marts, BI-facing models |

That split reflects real analytics engineering practice.

---

## Database Choice

Use **Postgres** locally.

**Why:**
- Simple and well understood
- Works cleanly with Docker
- Easy for Airflow connections
- Good enough for MVP scale
- Easy to query from Metabase or Superset

You do not need Spark or a lakehouse for the first version.

### Suggested Local Stack

Use Docker Compose with:
- Postgres (data warehouse)
- Airflow webserver, scheduler, triggerer
- Redis
- Postgres metadata DB for Airflow (or reuse one Postgres instance with multiple DBs)
- MinIO (S3-like object storage simulation)
- Metabase or Superset
- App container for parsing/transforms

MinIO is a good addition because it gives you S3-like object storage locally and makes the Terraform story more coherent.

### Bronze / Silver / Gold Storage Pattern in Practice

| Data | Storage |
|---|---|
| Raw JSON/CSV/XLSX/ZIP files | MinIO bucket (or cloud object storage) |
| Bronze/silver/gold tables | Postgres |

This mirrors a real-world pattern better than dumping everything into one database.

---

## Terraform: What to Provision

Use **AWS** (most marketable). Provision the cloud analog of your local architecture.

### Resources

**Lightweight cloud design:**
- S3 bucket for raw files
- RDS Postgres or Aurora Postgres
- ECS/Fargate or MWAA (later, if ambitious)
- Secrets Manager for credentials
- IAM roles/policies
- CloudWatch log groups
- Optionally: EC2 instance for Airflow (avoids managed Airflow complexity)

For MVP, keep Terraform focused on **storage + database + secrets + IAM**.

### Recommended Terraform Scope

**Phase 1:**
- S3
- RDS Postgres
- Security group
- Subnet group
- Secrets Manager secret
- IAM user/role for app access

**Phase 2:**
- Container registry
- ECS task definition
- Scheduled ECS task or managed Airflow

This lets you say you used Terraform meaningfully without turning the project into an infra project.

---

## Metabase vs. Superset

For this project, choose **Metabase first**.

**Why:**
- Faster setup
- Easier for a portfolio reviewer to understand
- Cleaner dashboarding for business-style analysis
- Less overhead than Superset

Choose Superset only if you specifically want richer SQL lab experience, more advanced charting flexibility, or stronger open-source BI credibility.

---

## Compliance Scoring: How to Think About It Correctly

Do not claim true legal noncompliance unless your checks are tightly grounded in the CMS requirements. Instead, frame it as:
- Compliance signals
- Standardization score
- Data quality score
- MRF completeness score

**Suggested weighted score:**

| Component | Weight |
|---|---|
| File accessibility | 20% |
| Required field completeness | 20% |
| Coded service coverage | 20% |
| Payer naming quality | 15% |
| Numeric pricing completeness | 15% |
| Updated/recency signal | 10% |

**Separate flags for:**
- File unreachable
- No payer-specific rates
- No discounted cash price
- Missing coding fields
- Missing NPI
- Unusually high proportion of nulls

> The exact required field set should reflect the current CMS requirements and 2026 updates.

---

## A Realistic End-to-End Workflow

### Step 1: Hospital Target Registry
Create a table or YAML file listing hospitals to monitor.

**Fields:** `hospital_id`, `hospital_name`, `system_name`, `state`, `source_url`, `active_flag`

### Step 2: Discover and Download
For each active hospital:
1. Fetch the MRF URL
2. Inspect headers if possible
3. Download file if changed
4. Store raw file in object storage
5. Log file metadata

### Step 3: Parse Into Raw Row Records
Depending on file type: JSON, CSV, XLSX, ZIP.

**Output:** Row-wise raw JSON blobs in bronze table.

### Step 4: Standardize Fields
Map raw file structures into a canonical schema:
- Service description, code type, billing code
- Payer, plan
- Negotiated charge, gross charge, discounted cash price
- Min/max rates, allowed amount fields
- Setting, notes

### Step 5: Normalize Service and Payer Dimensions
Apply deterministic rules and mapping tables.

### Step 6: Load Silver Facts
Build standardized charge rows.

### Step 7: Compute Gold Marts
Aggregate price summaries, spread metrics, regional metrics, compliance metrics.

### Step 8: Run Tests
- Required key columns not null
- Charge values nonnegative
- Hospital IDs valid
- Source file records exist for all silver facts
- Gold mart row counts above thresholds

### Step 9: Refresh BI
Metabase dashboards query gold tables.

---

## Example Dashboards to Build

**Dashboard 1: Executive Overview**
- Hospitals monitored
- Hospitals parseable
- Total standardized service rows
- Hospitals with missing key fields
- Median cash vs. negotiated ratio

**Dashboard 2: Negotiated-Rate Variation**
- Top hospitals by widest spread
- Top services by highest cross-hospital variation
- Boxplots / percentile-style views by service

**Dashboard 3: Cash vs. Negotiated**
- Services where cash is cheaper than median commercial negotiated
- Hospital ranking by cash-to-negotiated ratio
- Distribution of ratios by hospital type

**Dashboard 4: Standardization and Compliance Signals**
- Score by hospital
- Missing fields heatmap
- Hospitals with stale or inaccessible files
- Coding completeness by system

**Dashboard 5: Geography**
- Map by state/region
- Regional median price variation
- Rural vs. urban comparisons
- Nonprofit vs. for-profit comparisons

---

## What I Would Not Do in Version 1

Do not start with:
- All U.S. hospitals
- LLM-driven normalization
- Spark
- Kubernetes
- Managed Airflow
- Complicated CDC
- Realtime streaming
- Insurance claims enrichment
- Patient cost estimator UI

These all make the project harder to finish and less legible.

---

## What Success Looks Like for the MVP

By the end of MVP, you should be able to demo this:

> I selected 20 hospitals across 3 states. The pipeline ingests each hospital's machine-readable file. Raw files are versioned in object storage. Parsing logic standardizes inconsistent file layouts into a canonical charge model. Airflow orchestrates incremental file-based refreshes. Postgres stores bronze/silver/gold layers. Metabase dashboards answer: where negotiated spread is widest, whether cash is lower than commercial negotiated rates, which hospitals have lower standardization/completeness, and how variation differs by region and hospital type.

That is already a very credible portfolio project.

---

## Exactly What You Should Do Next

### Phase 1: Lock the Project Shape
1. Create a repo named `hospital-price-transparency-pipeline`
2. Write a one-page project spec (objective, scope, MVP hospitals count, target questions, local stack, cloud stack)
3. Decide the MVP geography and hospital list size
4. Choose Metabase over Superset (unless strong reason otherwise)
5. Choose Postgres + MinIO + Airflow + Docker Compose

**Deliverable:** `README.md` with project goal, architecture diagram description, MVP scope, and technology choices.

### Phase 2: Find and Register Source Hospitals
Build a hospital target list.

```
hospital_id,hospital_name,system_name,state,city,source_url,active_flag
```

Start with 10 hospitals first, not 25. Manually locate each machine-readable file URL.

**Deliverable:** `config/hospitals.csv`

### Phase 3: Stand Up Local Infrastructure
Build `docker-compose.yml` with: postgres, minio, airflow-init, airflow-webserver, airflow-scheduler, airflow-triggerer, redis, metabase, app container.

**Deliverable:** Working containers — Airflow UI, Metabase UI, Postgres, and MinIO bucket all reachable.

### Phase 4: Build Raw Ingestion First
Before any normalization, implement:
- File downloader
- Content hash checker
- Raw file upload to MinIO
- Bronze file metadata load into Postgres

Then add parsers for JSON, CSV, XLSX, and ZIP-wrapped files.

**Deliverable:** `bronze_hospital_source_files`, `bronze_hospital_price_rows`, one hospital successfully ingested end to end.

### Phase 5: Define Canonical Schema
Write the canonical row schema for standardized charges explicitly before coding silver transformations.

**Deliverable:** `docs/canonical_schema.md` + DDL for silver tables.

### Phase 6: Service and Payer Normalization Maps
Create starter CSV mapping tables. Do not wait for these to be perfect — seed with common cases and iterate.

**Deliverable:** `mappings/service_normalization.csv`, `mappings/payer_normalization.csv`

### Phase 7: Build One Gold Mart
Do not build all marts at once. Build `gold_service_price_summary` first, then build dashboards around it.

### Phase 8: Wire Airflow
Only after the underlying code works should you build the DAG. Your DAG should call existing Python modules and SQL scripts.

### Phase 9: Add Terraform
Provision: S3, RDS Postgres, Secrets Manager, IAM. Keep Airflow local at first.

### Phase 10: Polish for Portfolio Value
Add: architecture diagram, data model diagram, sample dashboard screenshots, example findings, limitations section, roadmap section.

---

## Best Order of Implementation

1. Project spec
2. Hospital source registry
3. Docker Compose local stack
4. Bronze file ingestion
5. Raw row extraction
6. Canonical schema
7. Silver standardization
8. One gold mart
9. One dashboard
10. Airflow DAG
11. Terraform cloud resources
12. Expanded metrics and polish

That order minimizes wasted effort.
