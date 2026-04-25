"""Path and URI helpers used by runtime config defaults."""

from __future__ import annotations

from pathlib import Path


def get_project_root(start: Path | None = None) -> Path:
    """Return the nearest ancestor containing a repo marker."""
    base = (start or Path.cwd()).resolve()
    if base.is_file():
        base = base.parent

    for candidate in (base, *base.parents):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate

    # Safe fallback when invoked in unusual environments.
    return Path(__file__).resolve().parents[3]


def get_default_data_root(project_root: Path | None = None) -> Path:
    """Return the canonical local data root for this project."""
    return (project_root or get_project_root()).resolve() / "data"


def get_default_logs_root(project_root: Path | None = None) -> Path:
    """Return the canonical local logs root for this project."""
    return (project_root or get_project_root()).resolve() / "logs"


def to_storage_uri(path_or_uri: str | Path) -> str:
    """Normalize a local path/file URI to an absolute URI.

    Non-file URIs (s3://, gs://, etc.) are passed through unchanged.
    """
    if isinstance(path_or_uri, Path):
        return path_or_uri.resolve().as_uri()

    value = path_or_uri.strip()
    if not value:
        msg = "storage path/uri must be non-empty"
        raise ValueError(msg)

    if "://" not in value:
        return Path(value).resolve().as_uri()

    if value.startswith("file://"):
        local_path = value.removeprefix("file://")
        if local_path.startswith("localhost/"):
            local_path = local_path.removeprefix("localhost")
        return Path(local_path).resolve().as_uri()

    return value.rstrip("/")
