"""CLI entrypoints for the HPT pipeline."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer

from hpt.ingest.config import DownloadConfig, IngestConfig
from hpt.ingest.download import Outcome, download_all
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.logging.log import configure_logging, get_logger
from hpt.pipeline.ingest_snapshot import ingest_snapshot
from hpt.registry.loader import RegistryError, get_hospitals, load_registry
from hpt.registry.models import HospitalSource
from hpt.utils.string_utils import convert_string_to_list


cli = typer.Typer(help="Hospital Price Transparency pipeline CLI.", no_args_is_help=True)


@cli.command()
def ingest(
    hospital_ids: str | None = typer.Option(
        None,
        "--hospital-ids",
        help="Comma-separated hospital IDs to ingest. Omit to ingest all hospitals.",
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
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Set the logging level.",
    ),
) -> None:
    """Parse downloaded MRF files into Bronze Parquet."""

    exit_code = ingest_logic(
        hospital_ids=hospital_ids,
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
        registry_path=registry_path,
        log_level=log_level,
    )
    raise typer.Exit(code=exit_code)


def _registry_kwargs(registry_path: Path | None) -> dict[str, Path]:
    return {"path": registry_path} if registry_path is not None else {}


def _load_hospitals_for_target(
    log,
    hospital_ids: list[str] | str | None = None,
    registry_path: Path | None = None,
) -> list[HospitalSource] | None:
    if isinstance(hospital_ids, str):
        hospital_ids = convert_string_to_list(hospital_ids)
    if hospital_ids is None:
        try:
            return load_registry(**_registry_kwargs(registry_path))
        except RegistryError as exc:
            log.error("registry_error", extra={"error": str(exc)})
            return None
    try:
        hospitals = get_hospitals(hospital_ids, **_registry_kwargs(registry_path))
        log.info(
            "target_selected",
            extra={
                "hospital_ids": hospital_ids,
                "mode": "selected",
            },
        )
        return hospitals
    except (KeyError, RegistryError) as exc:
        log.error("registry_error", extra={"error": str(exc)})
        return None


def ingest_logic(
    hospital_ids: list[str] | str | None = None,
    bronze_root: Path | None = None,
    quarantine_root: Path | None = None,
    registry_path: Path | None = None,
    log_level: str = "INFO",
) -> int:
    """Run ingest logic and return a process-style exit code."""
    try:
        cfg = IngestConfig.from_env(
            hospital_ids=hospital_ids,
            bronze_root=bronze_root,
            quarantine_root=quarantine_root,
            registry_path=registry_path,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    configure_logging(log_level=log_level)
    log = get_logger("cli.ingest")
    log.info(
        "ingest_run_start",
        extra={
            "mode": "all" if cfg.hospital_ids is None else "selected",
            "hospital_ids": cfg.hospital_ids,
            "registry_path": str(cfg.registry_path) if cfg.registry_path else None,
            "raw_base_uri": cfg.storage.raw_base_uri,
            "bronze_root": str(cfg.storage.bronze_root),
            "quarantine_root": str(cfg.storage.quarantine_root),
        },
    )
    log.debug(
        "ingest_config",
        extra={
            "hospital_ids": cfg.hospital_ids,
            "storage": {
                "raw_base_uri": cfg.storage.raw_base_uri,
                "bronze_root": str(cfg.storage.bronze_root),
                "quarantine_root": str(cfg.storage.quarantine_root),
            },
            "registry_path": str(cfg.registry_path) if cfg.registry_path else None,
        },
    )

    try:
        storage = BronzeStorage(cfg.storage.raw_base_uri)
        snapshots = SnapshotManager(storage)

        hospitals = _load_hospitals_for_target(
            log,
            cfg.hospital_ids,
            cfg.registry_path,
        )
        log.info("hospitals: %s", [h.hospital_id for h in hospitals])
        if hospitals is None:
            return 2
        log.info("ingest_targets_ready", extra={"hospital_count": len(hospitals)})

        failures = 0
        for hospital in hospitals:
            hid = hospital.hospital_id
            log.info("ingest_hospital_start", extra={"hospital_id": hid})
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

        log.info(
            "ingest_run_complete",
            extra={"hospital_count": len(hospitals), "failures": failures},
        )
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
    hospital_ids: str | None = typer.Option(
        None,
        "--hospital-ids",
        help="Comma-separated hospital IDs to download. Omit to download all hospitals.",
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
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Set the logging level.",
    )
) -> None:
    """Download source MRF files."""

    exit_code = download_logic(
        hospital_ids=hospital_ids,
        dry_run=dry_run,
        force=force,
        registry_path=registry_path,
        log_level=log_level,
    )

    raise typer.Exit(code=exit_code)


def download_logic(
    hospital_ids: list[str] | str | None = None,
    dry_run: bool = False,
    force: bool = False,
    registry_path: Path | None = None,
    log_level: str = "INFO",
) -> int:
    """Run download logic and return a process-style exit code."""
    try:
        cfg = DownloadConfig.from_env(
            hospital_ids=hospital_ids,
            dry_run=dry_run,
            force=force,
            registry_path=registry_path,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    configure_logging(log_level)
    log = get_logger("cli.download")
    log.info(
        "download_run_start",
        extra={
            "mode": "all" if cfg.hospital_ids is None else "selected",
            "hospital_ids": cfg.hospital_ids,
            "dry_run": cfg.dry_run,
            "force": cfg.force,
            "registry_path": str(cfg.registry_path) if cfg.registry_path else None,
            "raw_base_uri": cfg.storage.raw_base_uri,
        },
    )
    log.debug(
        "download_config",
        extra={
            "storage": {"raw_base_uri": cfg.storage.raw_base_uri},
            "client": {
                "connect_timeout_s": cfg.client.connect_timeout_s,
                "read_timeout_s": cfg.client.read_timeout_s,
                "timeout_s": cfg.client.timeout_s,
                "retries": cfg.client.retries,
                "user_agent": cfg.client.user_agent,
            },
            "dry_run": cfg.dry_run,
            "force": cfg.force,
        },
    )

    try:
        storage = BronzeStorage(cfg.storage.raw_base_uri)
        snapshots = SnapshotManager(storage)

        hospitals = _load_hospitals_for_target(
            log,
            cfg.hospital_ids,
            cfg.registry_path,
        )
        if hospitals is None:
            return 2
        log.info("download_targets_ready", extra={"hospital_count": len(hospitals)})

        results = download_all(hospitals, storage, snapshots, cfg)

        counts = Counter(r.outcome for r in results)
        summary = {o.value: counts.get(o, 0) for o in Outcome}
        log.info("run_summary", extra=summary)
        log.info(
            "download_run_complete",
            extra={"hospital_count": len(results), "failed": counts.get(Outcome.FAILED, 0)},
        )

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
