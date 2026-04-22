"""CLI entrypoints for the HPT pipeline."""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

import click

from hpt.ingest.config import IngestConfig
from hpt.ingest.download import Outcome, download_all, download_hospital, _build_client
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.pipeline.ingest_snapshot import ingest_snapshot
from hpt.registry.loader import RegistryError, get_hospital, load_registry


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if hasattr(record, "hospital_id"):
            payload["hospital_id"] = record.hospital_id  # type: ignore[attr-defined]
        for key in ("file_hash", "bytes", "duration_s", "snapshot_id", "error", "url"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        return json.dumps(payload)


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger("hpt")
    root.handlers = [handler]
    root.setLevel(logging.INFO)


@click.group()
def cli() -> None:
    """Hospital Price Transparency pipeline CLI."""


@cli.command()
@click.option(
    "--hospital-id",
    default=None,
    help="Ingest the current snapshot for a single hospital.",
)
@click.option(
    "--all",
    "ingest_all",
    is_flag=True,
    help="Ingest the current snapshot for every hospital in the registry.",
)
@click.option(
    "--bronze-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data/bronze"),
    show_default=True,
    help="Directory where Bronze Parquet partitions are written.",
)
@click.option(
    "--quarantine-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data/quarantine"),
    show_default=True,
    help="Directory where records that fail Pydantic validation are written.",
)
def ingest(
    hospital_id: str | None,
    ingest_all: bool,
    bronze_root: Path,
    quarantine_root: Path,
) -> None:
    """Parse downloaded MRF files into Bronze Parquet."""
    if not hospital_id and not ingest_all:
        raise click.UsageError("Provide --hospital-id <id> or --all.")

    _configure_logging()
    log = logging.getLogger("hpt.cli.ingest")

    try:
        cfg = IngestConfig.from_env()
        storage = BronzeStorage(cfg.bronze_base_uri)
        snapshots = SnapshotManager(storage)

        if hospital_id:
            try:
                hospitals = [get_hospital(hospital_id)]
            except (KeyError, RegistryError) as exc:
                log.error("registry_error", extra={"error": str(exc)})
                sys.exit(2)
        else:
            try:
                hospitals = load_registry()
            except RegistryError as exc:
                log.error("registry_error", extra={"error": str(exc)})
                sys.exit(2)

        failures = 0
        for hospital in hospitals:
            hid = hospital.hospital_id
            snapshot = snapshots.get_current_snapshot(hid)
            if snapshot is None:
                log.warning(
                    "no_snapshot",
                    extra={"hospital_id": hid, "error": "no current snapshot"},
                )
                failures += 1
                continue

            try:
                summary = ingest_snapshot(
                    snapshot=snapshot,
                    hospital_config=hospital.model_dump(),
                    storage=storage,
                    bronze_root=bronze_root,
                    quarantine_root=quarantine_root,
                )
                log.info("ingested", extra=summary)
            except NotImplementedError as exc:
                log.error(
                    "unsupported_format",
                    extra={
                        "hospital_id": hid,
                        "snapshot_id": snapshot.snapshot_id,
                        "error": str(exc),
                    },
                )
                failures += 1
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "ingest_failed: %s",
                    exc,
                    extra={
                        "hospital_id": hid,
                        "snapshot_id": snapshot.snapshot_id,
                        "error": str(exc),
                    },
                )
                failures += 1

        if failures and failures == len(hospitals):
            sys.exit(2)
        if failures:
            sys.exit(1)

    except RegistryError as exc:
        log.error("registry_error", extra={"error": str(exc)})
        sys.exit(2)


@cli.command()
@click.option("--hospital-id", default=None, help="Download a single hospital by ID.")
@click.option("--all", "run_all", is_flag=True, help="Download every hospital in the registry.")
@click.option("--dry-run", is_flag=True, help="Resolve URLs and report without fetching.")
@click.option("--force", is_flag=True, help="Re-download even if registry is unchanged.")
def download(
    hospital_id: str | None,
    run_all: bool,
    dry_run: bool,
    force: bool,
) -> None:
    """Download source MRF files."""
    if not hospital_id and not run_all:
        raise click.UsageError("Provide --hospital-id <id> or --all.")

    _configure_logging()
    log = logging.getLogger("hpt.cli.download")

    try:
        cfg = IngestConfig.from_env()
        storage = BronzeStorage(cfg.bronze_base_uri)
        snapshots = SnapshotManager(storage)

        if hospital_id:
            try:
                hospital = get_hospital(hospital_id)
            except (KeyError, RegistryError) as exc:
                log.error("registry_error", extra={"error": str(exc)})
                sys.exit(2)

            client = _build_client(cfg)
            try:
                result = download_hospital(
                    hospital, storage, snapshots, client, dry_run=dry_run, force=force
                )
            finally:
                client.close()
            results = [result]
        else:
            try:
                hospitals = load_registry()
            except RegistryError as exc:
                log.error("registry_error", extra={"error": str(exc)})
                sys.exit(2)
            results = download_all(
                hospitals, storage, snapshots, cfg, dry_run=dry_run, force=force
            )

        counts = Counter(r.outcome for r in results)
        summary = {o.value: counts.get(o, 0) for o in Outcome}
        log.info("run_summary", extra=summary)

        if counts.get(Outcome.FAILED, 0) == len(results):
            sys.exit(2)
        elif counts.get(Outcome.FAILED, 0) > 0:
            sys.exit(1)

    except RegistryError as exc:
        log.error("registry_error", extra={"error": str(exc)})
        sys.exit(2)
