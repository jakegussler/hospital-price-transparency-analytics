"""Build a synthetic multi-snapshot validation corpus for service-item identity.

Why this exists
---------------
Decision 0014 derives a deterministic, within-hospital ``service_item_id`` whose
whole purpose is *cross-snapshot continuity*: the same charge item must carry the
same id across successive MRF publications of one hospital, so Gold can track
price-over-time. Under the default ``current_only`` retention every hospital
holds exactly one snapshot, so ``snapshot_count = 1`` everywhere and that key has
never actually matched an item to itself across files (remaining-steps.md s2.4).

You cannot get a second snapshot organically: ``hpt download`` dedupes by file
hash, so a re-download of an unchanged file writes no new snapshot, and real
republished files are gated on time / orchestration. This script manufactures a
controlled second snapshot for a handful of fictional test hospitals by writing
two hand-authored CSV-tall MRF files per hospital and running them through the
real parser -> Bronze path, so the deterministic id is exercised on
realistically-shaped data without waiting for orchestration.

What it proves (after a full-refresh dbt build under ``all_snapshots`` retention)
--------------------------------------------------------------------------------
Each test hospital embeds labeled mutation classes between snapshot v1 and v2:

* continuity         -- identical code + description recurs -> same id, snapshot_count = 2
* drift tolerance    -- word-order / punctuation drift -> same id (token signature)
* price immateriality-- only the dollar amount changes -> same id
* drug quantity      -- only drug_unit changes (excluded from identity) -> same id
* mint on rewrite    -- token-set-changing rewrite -> NEW id; old id retires at v1
* new item           -- appears only in v2 -> snapshot_count = 1, minted in latest
* over-merge signal  -- two items share one specific code + token-equal
                        descriptions in a snapshot -> slv_audit__service_item_overmerge finding

Isolation
---------
The corpus is written to a dedicated, isolated storage root (default
``data/multi_snapshot_validation/``), NOT the production Bronze under
``data/bronze``. This keeps synthetic charge data out of the real corpus: a
normal production dbt run never reads it, and there is no way for ``clean`` to
delete real data. The two fictional hospitals live in a dedicated fixtures seed
(``transform/seeds/fixtures/hospitals_validation_fixtures.csv``), kept out of the
registry-faithful ``hospitals`` seed. They are unioned into ``slv_base__hospitals``
only when ``HPT_INCLUDE_VALIDATION_FIXTURES=true`` (so the service-item referential
test passes during validation); a normal production run never sees them.

Usage
-----
    .venv/bin/python scripts/build_multi_snapshot_corpus.py build
    .venv/bin/python scripts/build_multi_snapshot_corpus.py list
    .venv/bin/python scripts/build_multi_snapshot_corpus.py clean
    # override the isolated root with --root /some/dir

``build`` is idempotent: snapshot ids are derived deterministically, so re-running
overwrites the same raw files, metadata, and Bronze partitions rather than minting
new snapshots.

Validating the result is OUTSIDE the agent dbt-safety envelope (it needs more than
one snapshot per hospital materialized at once). After ``build``, materialize and
inspect with ``all_snapshots`` retention against this isolated root -- see
docs/development/multi-snapshot-validation.md for the exact commands.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import posixpath
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from hpt.ingest.config import StorageConfig
from hpt.ingest.snapshot import SnapshotManager, SnapshotRecord
from hpt.ingest.storage import BronzeStorage
from hpt.pipeline.ingest_snapshot import ingest_snapshot
from hpt.utils.paths import to_storage_uri

logger = logging.getLogger("hpt.scripts.multi_snapshot_corpus")

# Isolated storage root: the synthetic corpus lives here, never in production
# Bronze. Under data/ so it is git-ignored runtime output regenerable from this
# script. Override with --root.
_DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "multi_snapshot_validation"

# Stable namespace so snapshot ids are reproducible across runs and quotable in
# docs. Derived from a fixed string, not random, so ``build`` stays idempotent.
_SNAPSHOT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "hpt.multi-snapshot-validation")

# Fictional hospital id prefix. Deliberately unlike any registry id so the test
# corpus is obvious in Silver output and easy to target for cleanup.
_HOSPITAL_PREFIX = "zzz-msval"

# The CSV-tall charge-column header (CMS pipe-delimited). One code slot is enough
# for every identity basis we exercise; drug rows use the drug_* columns.
_CHARGE_HEADER = (
    "description,code|1,code|1|type,setting,billing_class,"
    "drug_unit_of_measurement,drug_type_of_measurement,"
    "standard_charge|gross,standard_charge|negotiated_dollar,"
    "standard_charge|methodology,payer_name,plan_name,count"
)

_META_HEADER = (
    "hospital_name,last_updated_on,version,location_name,hospital_address,"
    "license_number|TN,type_2_npi"
)


@dataclass(frozen=True)
class ChargeRow:
    """One CSV-tall charge row. Only identity-relevant fields are modeled; the
    rest carry sensible constant defaults so the file stays a valid MRF."""

    description: str
    code: str = ""
    code_type: str = ""
    setting: str = "outpatient"
    billing_class: str = "facility"
    drug_unit: str = ""
    drug_type: str = ""
    gross: str = "500"
    negotiated_dollar: str = "400"
    payer_name: str = "Aetna"
    plan_name: str = "PPO"
    count: str = "0"

    def to_csv(self) -> str:
        return ",".join(
            [
                self.description,
                self.code,
                self.code_type,
                self.setting,
                self.billing_class,
                self.drug_unit,
                self.drug_type,
                self.gross,
                self.negotiated_dollar,
                "fee schedule",
                self.payer_name,
                self.plan_name,
                self.count,
            ]
        )


@dataclass(frozen=True)
class SnapshotSpec:
    """One snapshot of one hospital: a date and its charge rows."""

    label: str  # e.g. "v1"
    ingested_on: datetime
    rows: list[ChargeRow]


@dataclass(frozen=True)
class HospitalSpec:
    """A fictional hospital and its ordered snapshots (oldest first)."""

    slug: str
    hospital_name: str
    snapshots: list[SnapshotSpec] = field(default_factory=list)

    @property
    def hospital_id(self) -> str:
        return f"{_HOSPITAL_PREFIX}-{self.slug}"


def _mrf_text(hospital: HospitalSpec, snapshot: SnapshotSpec) -> str:
    meta_values = (
        f"{hospital.hospital_name},{snapshot.ingested_on:%Y-%m-%d},2.0.0,"
        "Main Campus,123 Test St,TST-001,1234567893"
    )
    lines = [_META_HEADER, meta_values, _CHARGE_HEADER]
    lines.extend(row.to_csv() for row in snapshot.rows)
    return "\n".join(lines) + "\n"


def _snapshot_id(hospital_id: str, label: str) -> str:
    return str(uuid.uuid5(_SNAPSHOT_NAMESPACE, f"{hospital_id}:{label}"))


# --------------------------------------------------------------------------- #
# Corpus definition. Each mutation between v1 and v2 is commented inline so the
# expected continuity / drift / mint / over-merge behavior is auditable here.
# --------------------------------------------------------------------------- #
def _corpus() -> list[HospitalSpec]:
    v1_date = datetime(2025, 1, 1, tzinfo=UTC)
    v2_date = datetime(2025, 6, 1, tzinfo=UTC)

    continuity = HospitalSpec(
        slug="continuity",
        hospital_name="ZZZ Multi-Snapshot Continuity Test Hospital",
        snapshots=[
            SnapshotSpec(
                label="v1",
                ingested_on=v1_date,
                rows=[
                    # specific_code: recurs unchanged-in-tokens across snapshots.
                    ChargeRow("CT ABDOMEN W/ CONTRAST", "74160", "CPT"),
                    # specific_code: will be heavily rewritten in v2 (mint).
                    ChargeRow("CT HEAD WITHOUT CONTRAST", "70450", "CPT"),
                    # specific_code (HCPCS): fully stable.
                    ChargeRow("DEXAMETHASONE INJECTION", "J1100", "HCPCS"),
                    # categorical_code only (revenue code, no specific code).
                    ChargeRow("PHARMACY GENERAL", "0250", "RC"),
                    # uncoded.
                    ChargeRow("MISC ROOM SUPPLY", "", ""),
                    # specific_code + drug signature (NDC + unit); qty varies in v2.
                    ChargeRow(
                        "AMOXICILLIN 500MG CAP",
                        "12345678901",
                        "NDC",
                        drug_unit="1",
                        drug_type="EA",
                    ),
                ],
            ),
            SnapshotSpec(
                label="v2",
                ingested_on=v2_date,
                rows=[
                    # continuity + word-order drift + price change -> SAME id.
                    ChargeRow(
                        "CT W/ CONTRAST ABDOMEN",
                        "74160",
                        "CPT",
                        gross="550",
                        negotiated_dollar="420",
                    ),
                    # token-set-changing rewrite -> NEW id; the v1 70450 id retires.
                    ChargeRow("CT BRAIN STUDY NONCONTRAST IMAGING", "70450", "CPT"),
                    # unchanged -> SAME id.
                    ChargeRow("DEXAMETHASONE INJECTION", "J1100", "HCPCS"),
                    # unchanged -> SAME id.
                    ChargeRow("PHARMACY GENERAL", "0250", "RC"),
                    # unchanged -> SAME id.
                    ChargeRow("MISC ROOM SUPPLY", "", ""),
                    # drug quantity change only (excluded from identity) -> SAME id.
                    ChargeRow(
                        "AMOXICILLIN 500MG CAP",
                        "12345678901",
                        "NDC",
                        drug_unit="10",
                        drug_type="EA",
                    ),
                    # brand-new item, v2 only -> snapshot_count 1, minted in latest.
                    ChargeRow("OFFICE VISIT LEVEL 3 ESTABLISHED", "99213", "CPT"),
                ],
            ),
        ],
    )

    overmerge = HospitalSpec(
        slug="overmerge",
        hospital_name="ZZZ Multi-Snapshot Over-Merge Test Hospital",
        snapshots=[
            SnapshotSpec(
                label="v1",
                ingested_on=v1_date,
                rows=[
                    # Two genuinely distinct items (different billing context) that
                    # share one specific code AND token-equal descriptions, so the
                    # deterministic key intentionally merges them. Surfaces in
                    # slv_audit__service_item_overmerge with source_items > 1 and
                    # distinct_descriptions > 1, while staying well under the
                    # over-merge guard threshold (> 10).
                    ChargeRow(
                        "BLOOD DRAW VENIPUNCTURE",
                        "36415",
                        "CPT",
                        billing_class="facility",
                    ),
                    ChargeRow(
                        "VENIPUNCTURE BLOOD DRAW",
                        "36415",
                        "CPT",
                        billing_class="professional",
                    ),
                    # An ordinary, cleanly-identified item alongside it.
                    ChargeRow("CHEST XRAY 2 VIEWS", "71046", "CPT"),
                ],
            ),
            SnapshotSpec(
                label="v2",
                ingested_on=v2_date,
                rows=[
                    # Same over-merge shape recurs -> the finding persists across
                    # snapshots and snapshot_count for the merged id is 2.
                    ChargeRow(
                        "BLOOD DRAW VENIPUNCTURE",
                        "36415",
                        "CPT",
                        billing_class="facility",
                    ),
                    ChargeRow(
                        "VENIPUNCTURE BLOOD DRAW",
                        "36415",
                        "CPT",
                        billing_class="professional",
                    ),
                    ChargeRow("CHEST XRAY 2 VIEWS", "71046", "CPT"),
                ],
            ),
        ],
    )

    return [continuity, overmerge]


# --------------------------------------------------------------------------- #
# Build / clean drivers
# --------------------------------------------------------------------------- #
def _write_raw_file(
    storage: BronzeStorage,
    hospital_id: str,
    filename: str,
    ingested_at: datetime,
    content: str,
) -> tuple[str, str]:
    """Write a raw MRF file and return (destination_path, file_hash)."""
    data = content.encode("utf-8")
    file_hash = hashlib.sha256(data).hexdigest()
    dest = storage.raw_path(hospital_id, filename, ingested_at=ingested_at)
    storage.makedirs(posixpath.dirname(dest))
    with storage.open(dest, "wb") as fh:
        fh.write(data)
    return dest, file_hash


def build(storage: BronzeStorage, cfg: StorageConfig) -> None:
    snapshots = SnapshotManager(storage)
    for hospital in _corpus():
        for spec in hospital.snapshots:
            filename = f"{hospital.slug}_{spec.label}.csv"
            content = _mrf_text(hospital, spec)
            dest, file_hash = _write_raw_file(
                storage, hospital.hospital_id, filename, spec.ingested_on, content
            )
            record = SnapshotRecord(
                snapshot_id=_snapshot_id(hospital.hospital_id, spec.label),
                hospital_id=hospital.hospital_id,
                source_url=f"synthetic://multi-snapshot-validation/{filename}",
                source_file_name=filename,
                file_hash=file_hash,
                ingested_at=spec.ingested_on,
                valid_from=spec.ingested_on,
            )
            # Append-only metadata write (idempotent via deterministic id).
            snapshots._write_record(record)  # noqa: SLF001 -- maintenance script
            summary = ingest_snapshot(
                snapshot=record,
                hospital_config={"hospital_id": hospital.hospital_id},
                storage=storage,
                bronze_root=cfg.bronze_root,
                quarantine_root=cfg.quarantine_root,
            )
            logger.info(
                "ingested test snapshot %s (%s %s) raw=%s rows=%s",
                record.snapshot_id,
                hospital.hospital_id,
                spec.label,
                posixpath.basename(dest),
                summary.get("bronze_row_counts"),
            )
    logger.info("Multi-snapshot validation corpus built. Snapshot ids:")
    _list()


def _list() -> None:
    for hospital in _corpus():
        print(f"{hospital.hospital_id}:")
        for spec in hospital.snapshots:
            print(
                f"  {spec.label} ({spec.ingested_on:%Y-%m-%d}) "
                f"-> {_snapshot_id(hospital.hospital_id, spec.label)}"
            )


def clean(storage: BronzeStorage, cfg: StorageConfig) -> None:
    # Raw files and snapshot metadata live under the fsspec storage root.
    for hospital in _corpus():
        for sub in ("raw", "metadata/hospital_mrf_snapshots"):
            path = posixpath.join(
                storage._base_uri,  # noqa: SLF001 -- maintenance script
                sub,
                f"hospital_id={hospital.hospital_id}",
            )
            if storage.fs.exists(path):
                storage.fs.rm(path, recursive=True)
                logger.info("removed %s", path)
    # Bronze partitions are keyed by snapshot_id across every table directory.
    snapshot_ids = {_snapshot_id(h.hospital_id, s.label) for h in _corpus() for s in h.snapshots}
    bronze_root = cfg.bronze_root
    if bronze_root.exists():
        for table_dir in bronze_root.iterdir():
            if not table_dir.is_dir():
                continue
            for sid in snapshot_ids:
                partition = table_dir / f"snapshot_id={sid}"
                if partition.exists():
                    shutil.rmtree(partition)
                    logger.info("removed %s", partition)
    logger.info(
        "Removed Bronze/raw/metadata for the test corpus. To drop already-built "
        "Silver rows, run: hpt clear-snapshot --snapshot-ids %s",
        ",".join(sorted(snapshot_ids)),
    )


def _isolated_storage_config(root: Path) -> StorageConfig:
    """A StorageConfig rooted entirely under *root* (never production Bronze)."""
    return StorageConfig(
        raw_base_uri=to_storage_uri(root),
        bronze_root=root / "bronze",
        quarantine_root=root / "quarantine",
        audit_root=root / "audit",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("build", "clean", "list"),
        help="build: write + ingest the corpus; clean: remove it; list: show snapshot ids.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_DEFAULT_ROOT,
        help=f"Isolated storage root for the corpus. Defaults to {_DEFAULT_ROOT}.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.action == "list":
        _list()
        return 0

    cfg = _isolated_storage_config(args.root)
    storage = BronzeStorage(cfg.raw_base_uri)
    logger.info("Using isolated corpus root: %s", args.root)
    if args.action == "build":
        build(storage, cfg)
    elif args.action == "clean":
        clean(storage, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
