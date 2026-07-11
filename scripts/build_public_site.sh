#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

: "${HPT_DUCKDB_PATH:?Set HPT_DUCKDB_PATH to the warehouse DuckDB path.}"
: "${HPT_BRONZE_ROOT:?Set HPT_BRONZE_ROOT to the Bronze Parquet root.}"
: "${HPT_AUDIT_ROOT:?Set HPT_AUDIT_ROOT to the audit Parquet root.}"
: "${HPT_RAW_STORAGE_BASE_URI:?Set HPT_RAW_STORAGE_BASE_URI to the raw storage URI.}"
: "${HPT_QUARANTINE_ROOT:?Set HPT_QUARANTINE_ROOT to the quarantine root.}"

echo "Downloading active hospital MRFs..."
hpt download

echo "Ingesting active hospital snapshots to Bronze..."
hpt ingest

echo "Exporting active hospital seed..."
hpt export-hospitals-seed

echo "Building per-snapshot Silver/staging/validation graph..."
hpt run-dbt \
  --per-snapshot \
  --full-refresh \
  --defer-tests \
  --seeds \
  --selector per_snapshot

echo "Building Gold dimensions..."
hpt run-dbt \
  --all-hospitals \
  --defer-tests \
  --seeds \
  --selector gold_dimension \
  --command build

echo "Building per-snapshot Gold fact and bridge..."
hpt run-dbt \
  --per-snapshot \
  --full-refresh \
  --defer-tests \
  --selector gold_per_snapshot

echo "Building Gold marts..."
hpt run-dbt \
  --all-hospitals \
  --defer-tests \
  --selector gold_marts \
  --command build

echo "Building Gold scorecards..."
hpt run-dbt \
  --all-hospitals \
  --defer-tests \
  --selector gold_scorecards \
  --command build

echo "Building Gold BI presentation marts..."
hpt run-dbt \
  --all-hospitals \
  --defer-tests \
  --selector gold_bi \
  --command build

echo "Running Evidence readiness checks..."
uv run python scripts/check_evidence_readiness.py

echo "Exporting Evidence artifacts..."
uv run python scripts/export_evidence_artifact.py --replace

echo "Installing Evidence dependencies and building static site..."
cd apps/evidence
npm ci
npm run sources
npm run build

if [[ -n "${HPT_PUBLIC_SITE_S3_URI:-}" ]]; then
  echo "Syncing Evidence build to ${HPT_PUBLIC_SITE_S3_URI}..."
  aws s3 sync build/ "$HPT_PUBLIC_SITE_S3_URI" --delete
fi

echo "Public site build complete."
