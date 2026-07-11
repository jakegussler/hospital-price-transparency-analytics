#!/usr/bin/env bash
#
# ec2_bootstrap.sh — one-shot EC2 provisioning + public-site build.
#
# Runs the manual steps to prepare an EC2 instance for the public site.
# (mount EBS, install packages, clone repo, create the Python env, install
# Evidence deps, persist runtime env vars) and then hands off to
# scripts/build_public_site.sh so the whole pipeline runs automatically.
#
# Usage on a fresh instance (Ubuntu 24.04 recommended):
#
#   # Standalone — the script clones the repo for you:
#   curl -fsSL <raw-url>/scripts/ec2_bootstrap.sh -o ec2_bootstrap.sh
#   REPO_URL=https://github.com/<you>/hospital-price-transparency.git \
#   HPT_PUBLIC_SITE_S3_URI=s3://hpt-public-site-<name>/ \
#     bash ec2_bootstrap.sh
#
#   # Or from inside an already-cloned repo:
#   HPT_PUBLIC_SITE_S3_URI=s3://hpt-public-site-<name>/ scripts/ec2_bootstrap.sh
#
# The script is idempotent: re-running it skips work that is already done
# (packages installed, volume mounted, repo cloned, venv present). To only set
# up the environment without building the site, pass SKIP_BUILD=1.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override any of these via the environment before running.
# ---------------------------------------------------------------------------
REPO_URL="${REPO_URL:-}"                              # git URL; required for standalone clone
DATA_MOUNT="${DATA_MOUNT:-/mnt/hpt}"                  # EBS mount point for all runtime state
DATA_DEVICE="${DATA_DEVICE:-}"                        # e.g. /dev/nvme1n1; auto-detected if empty
RUNTIME_DIR="${RUNTIME_DIR:-$DATA_MOUNT/runtime}"    # root for raw/bronze/duckdb/temp
REPO_DIR="${REPO_DIR:-$DATA_MOUNT/hospital-price-transparency}"
NODE_VERSION="${NODE_VERSION:-22}"
NVM_VERSION="${NVM_VERSION:-v0.40.3}"

# DuckDB tuning — defaults sized for a ~64 GB RAM / 500 GB EBS instance.
# Bump these for larger instances (see the docs table).
export HPT_DUCKDB_MEMORY_LIMIT="${HPT_DUCKDB_MEMORY_LIMIT:-48GiB}"
export HPT_DUCKDB_MAX_TEMP_DIRECTORY_SIZE="${HPT_DUCKDB_MAX_TEMP_DIRECTORY_SIZE:-250GiB}"
export HPT_DBT_THREADS="${HPT_DBT_THREADS:-1}"
export HPT_USER_AGENT="${HPT_USER_AGENT:-Mozilla/5.0 hpt-research-contact@example.com}"

# Optional: where the built static site is synced. If empty, build only, no S3.
export HPT_PUBLIC_SITE_S3_URI="${HPT_PUBLIC_SITE_S3_URI:-}"

SKIP_BUILD="${SKIP_BUILD:-0}"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# 0. Basic environment facts
# ---------------------------------------------------------------------------
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"

# ---------------------------------------------------------------------------
# 1. Mount the EBS data volume
# ---------------------------------------------------------------------------
if mountpoint -q "$DATA_MOUNT"; then
  log "Data volume already mounted at $DATA_MOUNT"
else
  log "Mounting EBS data volume at $DATA_MOUNT"
  if [[ -z "$DATA_DEVICE" ]]; then
    # Pick the largest unmounted, unpartitioned disk (the data EBS, not root).
    DATA_DEVICE="$(lsblk -dnp -o NAME,TYPE,MOUNTPOINT | awk '$2=="disk" && $3=="" {print $1}' | tail -n1)"
  fi
  if [[ -z "$DATA_DEVICE" ]]; then
    echo "ERROR: could not auto-detect the data volume. Set DATA_DEVICE=/dev/nvmeXn1 and re-run." >&2
    lsblk >&2
    exit 1
  fi
  echo "Using data device: $DATA_DEVICE"
  # Only format if the device has no filesystem yet (avoids wiping existing data).
  if ! sudo blkid "$DATA_DEVICE" >/dev/null 2>&1; then
    echo "No filesystem found; creating xfs on $DATA_DEVICE"
    sudo mkfs -t xfs "$DATA_DEVICE"
  else
    echo "Existing filesystem detected on $DATA_DEVICE; not reformatting."
  fi
  sudo mkdir -p "$DATA_MOUNT"
  sudo mount "$DATA_DEVICE" "$DATA_MOUNT"
  sudo chown -R "$RUN_USER:$RUN_GROUP" "$DATA_MOUNT"
fi

# ---------------------------------------------------------------------------
# 2. Install system packages
# ---------------------------------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then
  log "Installing system packages (apt)"
  sudo apt-get update -y
  sudo apt-get install -y git make build-essential curl unzip \
    python3 python3-venv python3-dev
else
  echo "WARNING: apt-get not found; assuming packages are already present." >&2
fi

# uv (used by the Evidence helper scripts)
if ! command -v uv >/dev/null 2>&1 && [[ ! -x "$HOME/.local/bin/uv" ]]; then
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# AWS CLI v2 (needed only when syncing to S3)
if ! command -v aws >/dev/null 2>&1; then
  log "Installing AWS CLI v2"
  tmp="$(mktemp -d)"
  arch="$(uname -m)"
  case "$arch" in
    x86_64) awszip="awscli-exe-linux-x86_64.zip" ;;
    aarch64) awszip="awscli-exe-linux-aarch64.zip" ;;
    *) awszip="awscli-exe-linux-x86_64.zip" ;;
  esac
  curl -fsSL "https://awscli.amazonaws.com/$awszip" -o "$tmp/awscliv2.zip"
  unzip -q "$tmp/awscliv2.zip" -d "$tmp"
  sudo "$tmp/aws/install" --update
  rm -rf "$tmp"
fi

# ---------------------------------------------------------------------------
# 3. Node via nvm
# ---------------------------------------------------------------------------
export NVM_DIR="$HOME/.nvm"
if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
  log "Installing nvm + Node $NODE_VERSION"
  curl -o- "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | bash
fi
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
if ! nvm ls "$NODE_VERSION" >/dev/null 2>&1; then
  nvm install "$NODE_VERSION"
fi
nvm use "$NODE_VERSION"

# ---------------------------------------------------------------------------
# 4. Locate or clone the repository
# ---------------------------------------------------------------------------
# If this script lives inside a checkout, use that. Otherwise clone REPO_URL.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/build_public_site.sh" && -f "$SCRIPT_DIR/../pyproject.toml" ]]; then
  REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  log "Using existing repository at $REPO_DIR"
elif [[ -d "$REPO_DIR/.git" ]]; then
  log "Repository already present at $REPO_DIR"
else
  if [[ -z "$REPO_URL" ]]; then
    echo "ERROR: REPO_URL is required to clone the repository (or run this script from inside a checkout)." >&2
    exit 1
  fi
  log "Cloning $REPO_URL into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

# ---------------------------------------------------------------------------
# 5. Python environment
# ---------------------------------------------------------------------------
if [[ ! -d "$REPO_DIR/.venv" ]]; then
  log "Creating Python virtual environment"
  python3 -m venv "$REPO_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$REPO_DIR/.venv/bin/activate"
log "Installing Python package (dev,warehouse) + dbt deps"
pip install --upgrade pip
pip install -e ".[dev,warehouse]"
make dbt-deps

# ---------------------------------------------------------------------------
# 6. Evidence dependencies
# ---------------------------------------------------------------------------
log "Installing Evidence npm dependencies"
(cd apps/evidence && npm ci)

# ---------------------------------------------------------------------------
# 7. Runtime environment variables (persisted to ~/.bashrc)
# ---------------------------------------------------------------------------
export HPT_RAW_STORAGE_BASE_URI="file://$RUNTIME_DIR"
export HPT_BRONZE_ROOT="$RUNTIME_DIR/bronze"
export HPT_QUARANTINE_ROOT="$RUNTIME_DIR/quarantine"
export HPT_AUDIT_ROOT="$RUNTIME_DIR/audit"
export HPT_REFERENCE_ROOT="$RUNTIME_DIR/reference/bronze"
export HPT_REFERENCE_RAW_ROOT="$RUNTIME_DIR/reference/raw"
export HPT_DUCKDB_PATH="$RUNTIME_DIR/hpt.duckdb"
export HPT_DUCKDB_TEMP_DIRECTORY="$RUNTIME_DIR/duckdb-temp"

mkdir -p "$RUNTIME_DIR" "$HPT_BRONZE_ROOT" "$HPT_QUARANTINE_ROOT" \
  "$HPT_AUDIT_ROOT" "$HPT_REFERENCE_ROOT" "$HPT_REFERENCE_RAW_ROOT" \
  "$HPT_DUCKDB_TEMP_DIRECTORY"

ENV_FILE="$HOME/.hpt_env"
log "Writing runtime env to $ENV_FILE (sourced from ~/.bashrc)"
cat >"$ENV_FILE" <<EOF
# Generated by scripts/ec2_bootstrap.sh — HPT runtime environment.
export NVM_DIR="$HOME/.nvm"
[ -s "\$NVM_DIR/nvm.sh" ] && . "\$NVM_DIR/nvm.sh"
export PATH="\$HOME/.local/bin:\$PATH"
export HPT_RAW_STORAGE_BASE_URI="$HPT_RAW_STORAGE_BASE_URI"
export HPT_BRONZE_ROOT="$HPT_BRONZE_ROOT"
export HPT_QUARANTINE_ROOT="$HPT_QUARANTINE_ROOT"
export HPT_AUDIT_ROOT="$HPT_AUDIT_ROOT"
export HPT_REFERENCE_ROOT="$HPT_REFERENCE_ROOT"
export HPT_REFERENCE_RAW_ROOT="$HPT_REFERENCE_RAW_ROOT"
export HPT_DUCKDB_PATH="$HPT_DUCKDB_PATH"
export HPT_DUCKDB_TEMP_DIRECTORY="$HPT_DUCKDB_TEMP_DIRECTORY"
export HPT_DUCKDB_MAX_TEMP_DIRECTORY_SIZE="$HPT_DUCKDB_MAX_TEMP_DIRECTORY_SIZE"
export HPT_DUCKDB_MEMORY_LIMIT="$HPT_DUCKDB_MEMORY_LIMIT"
export HPT_DBT_THREADS="$HPT_DBT_THREADS"
export HPT_USER_AGENT="$HPT_USER_AGENT"
export HPT_PUBLIC_SITE_S3_URI="$HPT_PUBLIC_SITE_S3_URI"
# Activate the project virtualenv for interactive shells.
[ -f "$REPO_DIR/.venv/bin/activate" ] && source "$REPO_DIR/.venv/bin/activate"
EOF

if ! grep -q "source ~/.hpt_env" "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# HPT runtime environment\nsource ~/.hpt_env\n' >>"$HOME/.bashrc"
fi

# ---------------------------------------------------------------------------
# 8. Build the public site
# ---------------------------------------------------------------------------
if [[ "$SKIP_BUILD" == "1" ]]; then
  log "SKIP_BUILD=1 — environment ready; not running build_public_site.sh"
  echo "Run it later with:  source ~/.hpt_env && scripts/build_public_site.sh"
  exit 0
fi

log "Starting public-site build (this is the long-running step)"
scripts/build_public_site.sh

log "Bootstrap + build complete."
if [[ -n "$HPT_PUBLIC_SITE_S3_URI" ]]; then
  echo "Site synced to: $HPT_PUBLIC_SITE_S3_URI"
fi
echo "New SSH sessions will auto-load the env via ~/.hpt_env."
