"""CLI entrypoints for the HPT pipeline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from hpt.ingest.config import DownloadConfig, IngestConfig
from hpt.ingest.download import Outcome, download_all
from hpt.ingest.snapshot import SnapshotManager, SnapshotRecord
from hpt.ingest.storage import BronzeStorage
from hpt.logging.log import LoggingRunPaths, configure_logging, get_logger
from hpt.pipeline.ingest_snapshot import ingest_snapshot
from hpt.registry.loader import RegistryError, get_hospitals, load_registry
from hpt.registry.models import HospitalSource
from hpt.registry.seed_export import get_default_hospitals_seed_path, write_hospitals_seed
from hpt.utils.string_utils import convert_string_to_list

cli = typer.Typer(help="Hospital Price Transparency pipeline CLI.", no_args_is_help=True)

FailureRecord = dict[str, Any]


@cli.command()
def ingest(
    hospital_ids: str | None = typer.Option(
        None,
        "--hospital-ids",
        help="Comma-separated hospital IDs to ingest. Omit to ingest all hospitals.",
    ),
    raw_base_uri: str | None = typer.Option(
        None,
        "--raw-base-uri",
        help=(
            "fsspec URI prefix for raw downloads and snapshot metadata "
            "(for example file:///.../data or s3://bucket/prefix). "
            "Defaults to HPT_RAW_STORAGE_BASE_URI or canonical project data root."
        ),
        show_default=False,
    ),
    bronze_root: Path | None = typer.Option(
        None,
        "--bronze-root",
        file_okay=False,
        dir_okay=True,
        help=(
            "Directory where parsed Bronze Parquet partitions are written. "
            "Defaults to HPT_BRONZE_ROOT or data/bronze."
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
        raw_base_uri=raw_base_uri,
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
        registry_path=registry_path,
        log_level=log_level,
    )
    raise typer.Exit(code=exit_code)


def _registry_kwargs(registry_path: Path | None) -> dict[str, Path]:
    return {"path": registry_path} if registry_path is not None else {}


@cli.command("export-hospitals-seed")
def export_hospitals_seed(
    output_path: Path | None = typer.Option(
        None,
        "--output-path",
        file_okay=True,
        dir_okay=False,
        help=(
            "CSV path to write. Defaults to transform/seeds/hospitals.csv "
            "under the project root."
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
    """Populate the dbt hospitals seed from the active hospital registry."""
    exit_code = export_hospitals_seed_logic(
        output_path=output_path,
        registry_path=registry_path,
    )
    raise typer.Exit(code=exit_code)


def export_hospitals_seed_logic(
    *,
    output_path: Path | None = None,
    registry_path: Path | None = None,
) -> int:
    """Run hospitals seed export logic and return a process-style exit code."""
    try:
        written_path = write_hospitals_seed(
            registry_path=registry_path,
            output_path=output_path or get_default_hospitals_seed_path(),
        )
    except RegistryError as exc:
        typer.echo(f"Registry error: {exc}", err=True)
        return 2

    typer.echo(f"Wrote hospitals seed: {written_path}")
    return 0


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
            "targets_selected",
            extra={
                "hospital_ids": hospital_ids,
                "mode": "selected",
            },
        )
        return hospitals
    except (KeyError, RegistryError) as exc:
        log.error("registry_error", extra={"error": str(exc)})
        return None


def _build_ingest_failure(
    hospital: HospitalSource,
    failure_type: str,
    message: str,
    *,
    snapshot: SnapshotRecord | None = None,
    exc: Exception | None = None,
) -> FailureRecord:
    record: FailureRecord = {
        "hospital_id": hospital.hospital_id,
        "hospital_name": hospital.canonical_hospital_name,
        "failure_type": failure_type,
        "message": message,
        "expected_format": hospital.mrf_source.expected_format,
        "registry_source_url": str(hospital.mrf_source.url),
    }
    if snapshot is not None:
        record.update(
            {
                "snapshot_id": snapshot.snapshot_id,
                "source_file_name": snapshot.source_file_name,
                "source_url": snapshot.source_url,
                "file_hash": snapshot.file_hash,
                "ingested_at": snapshot.ingested_at.isoformat(),
            }
        )
    if exc is not None:
        record["exception_type"] = type(exc).__name__
    return record


def _failure_log_extra(failure: FailureRecord) -> dict[str, Any]:
    extra = {key: value for key, value in failure.items() if key != "message"}
    extra["error"] = failure["message"]
    extra["failure_message"] = failure["message"]
    return extra


def _write_ingest_failure_artifacts(
    log_paths: LoggingRunPaths,
    failures: list[FailureRecord],
    *,
    hospital_count: int,
) -> dict[str, str]:
    failure_count = len(failures)
    text_path = log_paths.failures_dir / f"{log_paths.run_id}_ingest_failures.log"
    jsonl_path = log_paths.failures_dir / f"{log_paths.run_id}_ingest_failures.jsonl"
    generated_at = datetime.now(UTC).isoformat()

    lines = [
        "Ingest failure summary",
        f"run_id: {log_paths.run_id}",
        f"generated_at: {generated_at}",
        f"hospital_count: {hospital_count}",
        f"failure_count: {failure_count}",
        f"std_out_log: {log_paths.std_out_path}",
        f"json_log: {log_paths.json_path}",
        "",
    ]
    for index, failure in enumerate(failures, start=1):
        lines.extend(
            [
                f"{index}. {failure['hospital_id']} - {failure['failure_type']}",
                f"   message: {failure['message']}",
            ]
        )
        for key in (
            "hospital_name",
            "snapshot_id",
            "source_file_name",
            "source_url",
            "registry_source_url",
            "expected_format",
            "exception_type",
        ):
            if key in failure:
                lines.append(f"   {key}: {failure[key]}")
        lines.append("")

    text_path.write_text("\n".join(lines), encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for failure in failures:
            payload = {
                "run_id": log_paths.run_id,
                "generated_at": generated_at,
                "hospital_count": hospital_count,
                "failure_count": failure_count,
                **failure,
            }
            fh.write(json.dumps(payload, default=str, sort_keys=True) + "\n")

    return {
        "failure_summary_path": str(text_path),
        "failure_jsonl_path": str(jsonl_path),
    }


def ingest_logic(
    hospital_ids: list[str] | str | None = None,
    raw_base_uri: str | Path | None = None,
    bronze_root: Path | None = None,
    quarantine_root: Path | None = None,
    registry_path: Path | None = None,
    log_level: str = "INFO",
) -> int:
    """Run ingest logic and return a process-style exit code."""
    try:
        cfg = IngestConfig.from_env(
            hospital_ids=hospital_ids,
            raw_base_uri=raw_base_uri,
            bronze_root=bronze_root,
            quarantine_root=quarantine_root,
            registry_path=registry_path,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    log_paths = configure_logging(log_level=log_level)
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
            "std_out_log": str(log_paths.std_out_path),
            "json_log": str(log_paths.json_path),
            "failures_dir": str(log_paths.failures_dir),
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
        if hospitals is None:
            return 2
        log.info("hospitals: %s", [h.hospital_id for h in hospitals])
        log.info("ingest_targets_ready", extra={"hospital_count": len(hospitals)})

        failures: list[FailureRecord] = []
        for hospital in hospitals:
            hid = hospital.hospital_id
            log.info("ingest_hospital_start", extra={"hospital_id": hid})
            snapshot = snapshots.get_current_snapshot(hid)
            if snapshot is None:
                failure = _build_ingest_failure(
                    hospital,
                    "no_snapshot",
                    (
                        f"No current snapshot metadata found for hospital {hid}. "
                        "Run download before ingesting this hospital or check raw "
                        "storage metadata."
                    ),
                )
                log.warning("no_snapshot", extra=_failure_log_extra(failure))
                failures.append(failure)
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
                failure = _build_ingest_failure(
                    hospital,
                    "unsupported_format",
                    (
                        f"Snapshot {snapshot.snapshot_id} for hospital {hid} uses "
                        f"a source format this ingest path does not support: {exc}"
                    ),
                    snapshot=snapshot,
                    exc=exc,
                )
                log.error("unsupported_format", extra=_failure_log_extra(failure))
                failures.append(failure)
            except Exception as exc:  # noqa: BLE001
                failure = _build_ingest_failure(
                    hospital,
                    "ingest_failed",
                    (
                        f"Ingest failed for snapshot {snapshot.snapshot_id} "
                        f"for hospital {hid}: {exc}"
                    ),
                    snapshot=snapshot,
                    exc=exc,
                )
                log.exception(
                    "ingest_failed",
                    extra=_failure_log_extra(failure),
                )
                failures.append(failure)

        failure_artifacts: dict[str, str] = {}
        if failures:
            failure_artifacts = _write_ingest_failure_artifacts(
                log_paths,
                failures,
                hospital_count=len(hospitals),
            )
            log.error(
                "ingest_failures_summary",
                extra={
                    "hospital_count": len(hospitals),
                    "failure_count": len(failures),
                    "failures": failures,
                    **failure_artifacts,
                },
            )
        log.info(
            "ingest_run_complete",
            extra={
                "hospital_count": len(hospitals),
                "failure_count": len(failures),
                "failures": failures,
                **failure_artifacts,
            },
        )
        if failures and len(failures) == len(hospitals):
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
    raw_base_uri: str | None = typer.Option(
        None,
        "--raw-base-uri",
        help=(
            "fsspec URI prefix for raw downloads and snapshot metadata "
            "(for example file:///.../data or s3://bucket/prefix). "
            "Defaults to HPT_RAW_STORAGE_BASE_URI or canonical project data root."
        ),
        show_default=False,
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
        raw_base_uri=raw_base_uri,
        dry_run=dry_run,
        force=force,
        registry_path=registry_path,
        log_level=log_level,
    )

    raise typer.Exit(code=exit_code)


def download_logic(
    hospital_ids: list[str] | str | None = None,
    raw_base_uri: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    registry_path: Path | None = None,
    log_level: str = "INFO",
) -> int:
    """Run download logic and return a process-style exit code."""
    try:
        cfg = DownloadConfig.from_env(
            hospital_ids=hospital_ids,
            raw_base_uri=raw_base_uri,
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
