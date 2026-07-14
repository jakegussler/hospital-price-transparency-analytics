#!/usr/bin/env bash
#
# Manual, pipeline-free deploy of the Evidence public site (Path B1).
#
# Rebuilds the static Evidence app from the ALREADY-COMMITTED Parquet artifacts
# under apps/evidence/sources/hpt/data/ and syncs the build to the public S3
# bucket, then invalidates CloudFront. It does NOT run download/ingest/dbt or
# re-export data — use scripts/build_public_site.sh for that. This is the fast
# path for theme / copy / component changes only.
#
# Usage:
#   set -a; source .env.prod; set +a
#   scripts/deploy_site_manual.sh
#
# Required env (see .env.prod / docs/planning/AWS):
#   HPT_PUBLIC_SITE_S3_URI          e.g. s3://hpt-public-site-<suffix>
#   HPT_CLOUDFRONT_DISTRIBUTION_ID  e.g. E1A2B3C4D5E6F7
# Optional:
#   HPT_NODE_BIN_DIR   dir to prepend to PATH so the right node is used
#                      (default: /opt/homebrew/opt/node@22/bin if present).
#                      System node 25 is known-broken for this build.
#   AWS_PROFILE / AWS_REGION  standard AWS CLI credential selection.
#   SKIP_INVALIDATION=1  sync only; skip the CloudFront invalidation.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

: "${HPT_PUBLIC_SITE_S3_URI:?Set HPT_PUBLIC_SITE_S3_URI (e.g. s3://hpt-public-site-<suffix>).}"
: "${HPT_CLOUDFRONT_DISTRIBUTION_ID:?Set HPT_CLOUDFRONT_DISTRIBUTION_ID (the distribution serving the site).}"

# --- Pick the right node --------------------------------------------------
NODE_BIN_DIR="${HPT_NODE_BIN_DIR:-/opt/homebrew/opt/node@22/bin}"
if [[ -x "$NODE_BIN_DIR/node" ]]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi
echo "Using node: $(command -v node) ($(node --version))"

# --- Sanity: the committed data artifacts must be present -----------------
DATA_DIR="apps/evidence/sources/hpt/data"
if ! compgen -G "$DATA_DIR/*.parquet" >/dev/null; then
  echo "ERROR: no Parquet artifacts under $DATA_DIR." >&2
  echo "This script does not regenerate data. Run scripts/build_public_site.sh" >&2
  echo "if you actually need to rebuild the data from the pipeline." >&2
  exit 1
fi

# --- Build the static site ------------------------------------------------
echo "Building Evidence static site from committed artifacts..."
pushd apps/evidence >/dev/null
npm ci
npm run sources          # loads sources/hpt/data/*.parquet into the build
npm run build            # -> apps/evidence/build/

if [[ ! -f build/index.html ]]; then
  echo "ERROR: build/index.html missing; build did not succeed." >&2
  exit 1
fi
popd >/dev/null

# --- Publish --------------------------------------------------------------
echo "Syncing build/ to ${HPT_PUBLIC_SITE_S3_URI} ..."
aws s3 sync apps/evidence/build/ "$HPT_PUBLIC_SITE_S3_URI" --delete

if [[ "${SKIP_INVALIDATION:-0}" == "1" ]]; then
  echo "SKIP_INVALIDATION=1 — not invalidating CloudFront."
else
  echo "Invalidating CloudFront distribution ${HPT_CLOUDFRONT_DISTRIBUTION_ID} ..."
  aws cloudfront create-invalidation \
    --distribution-id "$HPT_CLOUDFRONT_DISTRIBUTION_ID" \
    --paths '/*' \
    --query 'Invalidation.{Id:Id,Status:Status}' \
    --output table
fi

echo "Manual site deploy complete."
