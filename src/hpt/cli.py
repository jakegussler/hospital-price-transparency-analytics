"""CLI entrypoints for the HPT pipeline."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer

from hpt.ingest.config import IngestConfig
from hpt.ingest.download import Outcome, download_all, download_hospital, _build_client
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.log import configure_logging, get_logger
from hpt.pipeline.ingest_snapshot import ingest_snapshot
from hpt.registry.loader import RegistryError, get_hospital, load_registry


cli = typer.Typer(help="Hospital Price Transparency pipeline CLI.", no_args_is_help=True)


@cli.command()
def ingest(
    hospital_id: str | None = typer.Option(
        None,
        "--hospital-id",
        help="Ingest the current snapshot for a single hospital.",
    ),
    ingest_all: bool = typer.Option(
        False,
        "--all",
        help="Ingest the current snapshot for every hospital in the registry.",
    ),
    bronze_root: Path = typer.Option(
        Path("data/bronze"),
        "--bronze-root",
        file_okay=False,
        dir_okay=True,
        help="Directory where Bronze Parquet partitions are written.",
        show_default=True,
    ),
    quarantine_root: Path = typer.Option(
        Path("data/quarantine"),
        "--quarantine-root",
        file_okay=False,
        dir_okay=True,
        help="Directory where records that fail Pydantic validation are written.",
        show_default=True,
    ),
) -> None:
    """Parse downloaded MRF files into Bronze Parquet."""
    try:
        exit_code = ingest_logic(
            hospital_id=hospital_id,
            ingest_all=ingest_all,
            bronze_root=bronze_root,
            quarantine_root=quarantine_root,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    raise typer.Exit(code=exit_code)


def _require_target_selection(hospital_id: str | None, run_all: bool) -> None:
    if not hospital_id and not run_all:
        raise ValueError("Provide --hospital-id <id> or --all.")


def ingest_logic(
    hospital_id: str | None,
    ingest_all: bool,
    bronze_root: Path,
    quarantine_root: Path,
) -> int:
    """Run ingest logic and return a process-style exit code."""
    _require_target_selection(hospital_id, ingest_all)

    configure_logging()
    log = get_logger("cli.ingest")

    try:
        cfg = IngestConfig.from_env()
        storage = BronzeStorage(cfg.bronze_base_uri)
        snapshots = SnapshotManager(storage)

        if hospital_id:
            try:
                hospitals = [get_hospital(hospital_id)]
            except (KeyError, RegistryError) as exc:
                log.error("registry_error", extra={"error": str(exc)})
                return 2
        else:
            try:
                hospitals = load_registry()
            except RegistryError as exc:
                log.error("registry_error", extra={"error": str(exc)})
                return 2

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
            return 2
        if failures:
            return 1
        return 0

    except RegistryError as exc:
        log.error("registry_error", extra={"error": str(exc)})
        return 2


@cli.command()
def download(
    hospital_id: str | None = typer.Option(
        None,
        "--hospital-id",
        help="Download a single hospital by ID.",
    ),
    run_all: bool = typer.Option(
        False,
        "--all",
        help="Download every hospital in the registry.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Resolve URLs and report without fetching.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-download even if registry is unchanged.",
    ),
) -> None:
    """Download source MRF files."""
    try:
        exit_code = download_logic(
            hospital_id=hospital_id,
            run_all=run_all,
            dry_run=dry_run,
            force=force,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    raise typer.Exit(code=exit_code)


def download_logic(
    hospital_id: str | None,
    run_all: bool,
    dry_run: bool,
    force: bool,
) -> int:
    """Run download logic and return a process-style exit code."""
    _require_target_selection(hospital_id, run_all)

    configure_logging()
    log = get_logger("cli.download")

    try:
        cfg = IngestConfig.from_env()
        storage = BronzeStorage(cfg.bronze_base_uri)
        snapshots = SnapshotManager(storage)

        if hospital_id:
            try:
                hospital = get_hospital(hospital_id)
            except (KeyError, RegistryError) as exc:
                log.error("registry_error", extra={"error": str(exc)})
                return 2

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
                return 2
            results = download_all(
                hospitals, storage, snapshots, cfg, dry_run=dry_run, force=force
            )

        counts = Counter(r.outcome for r in results)
        summary = {o.value: counts.get(o, 0) for o in Outcome}
        log.info("run_summary", extra=summary)

        if counts.get(Outcome.FAILED, 0) == len(results):
            return 2
        if counts.get(Outcome.FAILED, 0) > 0:
            return 1
        return 0

    except RegistryError as exc:
        log.error("registry_error", extra={"error": str(exc)})
        return 2


if __name__ == "__main__":
    cli()
