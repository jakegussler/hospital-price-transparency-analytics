"""Pipeline configuration sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestConfig:
    """Immutable configuration for the download / ingest layer.

    Every field maps to an environment variable with a sensible local default
    so the same code works in a developer shell, Docker Compose, and Airflow.
    """

    bronze_base_uri: str
    http_connect_timeout: float
    http_read_timeout: float
    http_retries: int
    user_agent: str
    http_timeout: float

    @classmethod
    def from_env(cls) -> IngestConfig:
        return cls(
            bronze_base_uri=os.environ.get("HPT_BRONZE_BASE_URI", "file://./data"),
            http_connect_timeout=float(os.environ.get("HPT_HTTP_CONNECT_TIMEOUT", "10")),
            http_read_timeout=float(os.environ.get("HPT_HTTP_READ_TIMEOUT", "300")),
            http_retries=int(os.environ.get("HPT_HTTP_RETRIES", "3")),
            user_agent=os.environ.get("HPT_USER_AGENT", "hpt-pipeline/0.1"),
            http_timeout=float(os.environ.get("HPT_HTTP_TIMEOUT", "60")),
        )
