"""CLI entrypoints for the HPT pipeline."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer

from hpt.ingest.config import DownloadConfig, IngestConfig
from hpt.ingest.download import Outcome, download_all
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.log import configure_logging, get_logger
from hpt.pipeline.ingest_snapshot import ingest_snapshot
from hpt.registry.loader import RegistryError, get_hospital, load_registry
from hpt.registry.models import HospitalSource


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
    bronze_root: Path | None = typer.Option(
        None,
        "--bronze-root",
        file_okay=False,
        dir_okay=True,
        help=(
            "Directory where parsed Bronze Parquet partitions are written. "
            "Defaults to HPT_PARSED_BRONZE_ROOT or data/bronze."
        ),
        show_default=False,
    ),
    quarantine_root: Path | None = typer.Option(
        None,
        "--quarantine-root",
        file_okay=False,
        dir_okay=True,
        help=(
            "Directory where records that fail Pydantic validation are written. "
            "Defaults to HPT_QUARANTINE_ROOT or data/quarantine."
        ),
        show_default=False,
    ),
    registry_path: Path | None = typer.Option(
        None,
        "--registry-path",
        file_okay=True,
        dir_okay=False,
        help=(
            "Override the hospital registry file. Defaults to HPT_REGISTRY_PATH "
            "or bundled registry."
        ),
        show_default=False,
    ),
) -> None:
    """Parse downloaded MRF files into Bronze Parquet."""
    try:
        cfg = IngestConfig.from_env(
            hospital_id=hospital_id,
            run_all=ingest_all,
            bronze_root=bronze_root,
            quarantine_root=quarantine_root,
            registry_path=registry_path,
        )
        exit_code = ingest_logic(cfg)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    raise typer.Exit(code=exit_code)


def _registry_kwargs(registry_path: Path | None) -> dict[str, Path]:
    return {"path": registry_path} if registry_path is not None else {}


def _load_hospitals_for_target(
    hospital_id: str | None,
    registry_path: Path | None,
    log,
) -> list[HospitalSource] | None:
    try:
        if hospital_id:
            return [get_hospital(hospital_id, **_registry_kwargs(registry_path))]
        return load_registry(**_registry_kwargs(registry_path))
    except (KeyError, RegistryError) as exc:
        log.error("registry_error", extra={"error": str(exc)})
        return None


def ingest_logic(cfg: IngestConfig) -> int:
    """Run ingest logic and return a process-style exit code."""
    configure_logging()
    log = get_logger("cli.ingest")

    try:
        storage = BronzeStorage(cfg.storage.raw_base_uri)
        snapshots = SnapshotManager(storage)

        hospitals = _load_hospitals_for_target(
            cfg.hospital_id,
            cfg.registry_path,
            log,
        )
        if hospitals is None:
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
                    bronze_root=cfg.storage.bronze_root,
                    quarantine_root=cfg.storage.quarantine_root,
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
    registry_path: Path | None = typer.Option(
        None,
        "--registry-path",
        file_okay=True,
        dir_okay=False,
        help=(
            "Override the hospital registry file. Defaults to HPT_REGISTRY_PATH "
            "or bundled registry."
        ),
        show_default=False,
    ),
) -> None:
    """Download source MRF files."""
    try:
        cfg = DownloadConfig.from_env(
            hospital_id=hospital_id,
            run_all=run_all,
            dry_run=dry_run,
            force=force,
            registry_path=registry_path,
        )
        exit_code = download_logic(cfg)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    raise typer.Exit(code=exit_code)


def download_logic(cfg: DownloadConfig) -> int:
    """Run download logic and return a process-style exit code."""
    configure_logging()
    log = get_logger("cli.download")

    try:
        storage = BronzeStorage(cfg.storage.raw_base_uri)
        snapshots = SnapshotManager(storage)

        hospitals = _load_hospitals_for_target(
            cfg.hospital_id,
            cfg.registry_path,
            log,
        )
        if hospitals is None:
            return 2

        results = download_all(hospitals, storage, snapshots, cfg)

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
