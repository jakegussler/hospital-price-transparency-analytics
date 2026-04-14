"""CLI entrypoints for the HPT pipeline."""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter

import click

from hpt.ingest.config import IngestConfig
from hpt.ingest.download import Outcome, download_all, download_hospital, _build_client
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
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
@click.argument("hospital_id", required=False)
def parse(hospital_id: str | None) -> None:
    """Parse source files into bronze parquet."""
    click.echo(f"parse: not yet implemented (hospital_id={hospital_id})")


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
