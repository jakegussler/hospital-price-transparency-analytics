## Objective

Build an end-to-end data pipeline that ingests, normalizes, and analyzes hospital machine-readable files (MRFs) published under the CMS Price Transparency Rule. The pipeline produces a bronze/silver/gold data model powering interactive dashboards that help consumers, employers, and researchers understand how hospital prices vary across facilities, payers, and geographies.

---

## MVP Scope

**15–20 hospitals** across **3 states**: Florida, Tennessee, and North Carolina.

Hospital mix:
- 2–3 academic medical centers
- 5–7 community hospitals
- 2–3 for-profit hospitals
- 3–5 nonprofit hospitals
- Spanning 2–4 health systems + several independents

---

## Target Questions

**Variation & Spread**
- How much do prices vary for the same procedure across hospitals in a region?
- Which shoppable services show the widest cross-hospital price range?

**Payer Dynamics**
- How do negotiated rates differ across major payers (BCBS, Aetna, UHC) at the same hospital?
- When is the cash/self-pay rate cheaper than negotiated commercial rates?

**Hospital Behavior**
- Do multi-hospital systems show consistent pricing across facilities?
- How do academic medical centers compare to community hospitals on price?

**Compliance & Data Quality**
- Which hospitals publish the most complete, standardized pricing data?
- Which hospitals show signs of low transparency (missing fields, stale files, no payer-specific rates)?

---

## Local Stack

| Component | Tool |
|---|---|
| Orchestration | Apache Airflow |
| Data Warehouse | PostgreSQL or DuckDB|
| Object Storage | MinIO (S3-compatible) |
| BI / Dashboards | Metabase |
| Containerization | Docker Compose |
| App Language | Python |
| Transformation | SQL (bronze → silver → gold) |

---

## Cloud Stack (AWS)

| Component | Service |
|---|---|
| Object Storage | S3 |
| Data Warehouse | RDS PostgreSQL or (???) |
| Secrets | Secrets Manager |
| Access Control | IAM roles/policies |
| Infrastructure | Terraform |
| Compute (later) | ECS/Fargate |

---

## Data Architecture

**Bronze** — Raw source files and extracted row-level records; preserved exactly as downloaded.

**Silver** — Standardized entities: hospitals, services (CPT/HCPCS normalized), payers (name-normalized), standard charge rows, compliance observations.

**Gold** — Analytics marts:
- `gold_service_price_summary` — spread metrics per hospital × service
- `gold_hospital_compliance_scorecard` — completeness and standardization scores
- `gold_region_service_variation` — cross-hospital variation by region and service

---

## Key Technical Decisions

- **Service normalization:** Tiered approach — billing code match → deterministic text rules → curated mapping table → fuzzy fallback
- **Payer normalization:** Mapping table grouping raw payer/plan names to normalized payer groups
- **Incremental loading:** File-level, hash-based — reprocess only when source file changes
- **Compliance scoring:** Weighted signal score across field completeness, coding coverage, payer naming quality, and file recency

---

## MVP Success Criteria

The pipeline can ingest MRFs for 15–20 hospitals, standardize pricing into a canonical schema, and serve Metabase dashboards answering: where negotiated-rate spread is widest, when cash prices beat commercial rates, which hospitals have lower data quality, and how prices vary by region and hospital type.
