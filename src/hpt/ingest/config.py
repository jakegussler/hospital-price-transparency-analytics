"""Runtime configuration for HPT ingest and download phases."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from hpt.utils.string_utils import convert_string_to_list


def _env_float(name: str, default: str) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: str) -> int:
    return int(os.environ.get(name, default))


def _registry_path_from_env(path: Path | None = None) -> Path | None:
    if path is not None:
        return path
    env_path = os.environ.get("HPT_REGISTRY_PATH")
    return Path(env_path) if env_path else None


def _normalize_hospital_ids(
    hospital_ids: list[str] | str | None,
) -> list[str] | None:
    if hospital_ids is None:
        return None
    if isinstance(hospital_ids, str):
        return convert_string_to_list(hospital_ids)
    return [hospital_id.strip().lower() for hospital_id in hospital_ids if hospital_id.strip()]


@dataclass(frozen=True)
class ClientConfig:
    """HTTP client settings for fetching hospital MRF source files."""

    connect_timeout_s: float = 10.0
    read_timeout_s: float = 300.0
    retries: int = 3
    user_agent: str = "hpt-pipeline/0.1"
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> ClientConfig:
        return cls(
            connect_timeout_s=_env_float("HPT_HTTP_CONNECT_TIMEOUT", "10"),
            read_timeout_s=_env_float("HPT_HTTP_READ_TIMEOUT", "300"),
            retries=_env_int("HPT_HTTP_RETRIES", "3"),
            user_agent=os.environ.get("HPT_USER_AGENT", "hpt-pipeline/0.1"),
            timeout_s=_env_float("HPT_HTTP_TIMEOUT", "60"),
        )


@dataclass(frozen=True)
class StorageConfig:
    """Storage roots for raw source files, parsed Bronze, and quarantine."""

    raw_base_uri: str = "file://./data"
    bronze_root: Path = Path("data/bronze")
    quarantine_root: Path = Path("data/quarantine")

    @classmethod
    def from_env(
        cls,
        *,
        bronze_root: Path | None = None,
        quarantine_root: Path | None = None,
    ) -> StorageConfig:
        return cls(
            raw_base_uri=os.environ.get("HPT_RAW_STORAGE_BASE_URI", "file://./data"),
            bronze_root=bronze_root
            or Path(os.environ.get("HPT_PARSED_BRONZE_ROOT", "data/bronze")),
            quarantine_root=quarantine_root
            or Path(os.environ.get("HPT_QUARANTINE_ROOT", "data/quarantine")),
        )


@dataclass(frozen=True)
class DownloadConfig:
    """Configuration for a complete download run."""

    hospital_ids: list[str] | str | None = None
    storage: StorageConfig = field(default_factory=StorageConfig.from_env)
    registry_path: Path | None = field(default_factory=_registry_path_from_env)
    client: ClientConfig = field(default_factory=ClientConfig.from_env)
    dry_run: bool = False
    force: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hospital_ids",
            _normalize_hospital_ids(self.hospital_ids),
        )

    @classmethod
    def from_env(
        cls,
        *,
        hospital_ids: list[str] | str | None = None,
        dry_run: bool = False,
        force: bool = False,
        registry_path: Path | None = None,
    ) -> DownloadConfig:
        return cls(
            hospital_ids=hospital_ids,
            storage=StorageConfig.from_env(),
            registry_path=_registry_path_from_env(registry_path),
            client=ClientConfig.from_env(),
            dry_run=dry_run,
            force=force,
        )


@dataclass(frozen=True)
class IngestConfig:
    """Configuration for a complete parse-to-Bronze ingest run."""

    hospital_ids: list[str] | str | None = None
    storage: StorageConfig = field(default_factory=StorageConfig.from_env)
    registry_path: Path | None = field(default_factory=_registry_path_from_env)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hospital_ids",
            _normalize_hospital_ids(self.hospital_ids),
        )

    @classmethod
    def from_env(
        cls,
        *,
        hospital_ids: list[str] | str | None = None,
        bronze_root: Path | None = None,
        quarantine_root: Path | None = None,
        registry_path: Path | None = None,
    ) -> IngestConfig:
        return cls(
            hospital_ids=hospital_ids,
            storage=StorageConfig.from_env(
                bronze_root=bronze_root,
                quarantine_root=quarantine_root,
            ),
            registry_path=_registry_path_from_env(registry_path),
        )
