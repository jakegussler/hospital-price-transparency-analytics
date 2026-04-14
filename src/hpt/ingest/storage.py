"""fsspec-backed bronze storage with Hive-style partitioning."""

from __future__ import annotations

import posixpath
import uuid
from datetime import UTC, datetime

import fsspec


class BronzeStorage:
    """Thin wrapper around an fsspec filesystem rooted at *base_uri*.

    All raw MRF files and snapshot metadata are written through this class
    so that swapping local disk for S3/MinIO is a config change, not a rewrite.
    """

    def __init__(self, base_uri: str) -> None:
        self._base_uri = base_uri.rstrip("/")
        self._fs, self._root = fsspec.core.url_to_fs(self._base_uri)

    # -- public helpers --------------------------------------------------------

    @property
    def fs(self) -> fsspec.AbstractFileSystem:
        return self._fs

    def raw_path(
        self,
        hospital_id: str,
        filename: str,
        ingested_at: datetime | None = None,
        file_hash: str | None = None,
    ) -> str:
        """Build the Hive-partitioned destination for a raw MRF file.

        Layout: ``{root}/raw/hospital_id={id}/ingested_at={YYYY-MM-DD}/{filename}``

        When *file_hash* is supplied **and** a file already exists for this
        hospital + date with a different name, the filename is suffixed with
        the short hash to avoid collisions.
        """
        if ingested_at is None:
            ingested_at = datetime.now(UTC)
        date_str = ingested_at.strftime("%Y-%m-%d")
        partition = posixpath.join(
            self._root,
            "raw",
            f"hospital_id={hospital_id}",
            f"ingested_at={date_str}",
        )
        final_name = self._collision_safe_name(partition, filename, file_hash)
        return posixpath.join(partition, final_name)

    def metadata_path(self, hospital_id: str, snapshot_id: str | None = None) -> str:
        """Return the directory (or file path) for snapshot Parquet metadata."""
        base = posixpath.join(
            self._root,
            "metadata",
            "hospital_mrf_snapshots",
            f"hospital_id={hospital_id}",
        )
        if snapshot_id is None:
            return base
        return posixpath.join(base, f"{snapshot_id}.parquet")

    def temp_path(self, hospital_id: str) -> str:
        """Return a unique temp path under ``{root}/.tmp/``."""
        return posixpath.join(
            self._root, ".tmp", f"{hospital_id}_{uuid.uuid4().hex[:12]}"
        )

    def open(self, path: str, mode: str = "rb"):  # noqa: A003
        """Open *path* via fsspec (pass-through)."""
        return self._fs.open(path, mode)

    def exists(self, path: str) -> bool:
        return self._fs.exists(path)

    def makedirs(self, path: str) -> None:
        self._fs.makedirs(path, exist_ok=True)

    def mv(self, src: str, dst: str) -> None:
        self._fs.makedirs(posixpath.dirname(dst), exist_ok=True)
        self._fs.mv(src, dst)

    def rm(self, path: str) -> None:
        if self._fs.exists(path):
            self._fs.rm(path)

    def ls(self, path: str) -> list[str]:
        if not self._fs.exists(path):
            return []
        return self._fs.ls(path, detail=False)

    # -- internals -------------------------------------------------------------

    def _collision_safe_name(
        self, partition_dir: str, filename: str, file_hash: str | None
    ) -> str:
        """Append short hash to *filename* if a different file already exists
        in *partition_dir* for the same day."""
        if file_hash is None:
            return filename
        if not self._fs.exists(partition_dir):
            return filename

        existing = self._fs.ls(partition_dir, detail=False)
        existing_names = {posixpath.basename(p) for p in existing}

        if filename not in existing_names:
            return filename

        stem, dot, ext = filename.rpartition(".")
        if not dot:
            stem, ext = filename, ""
        else:
            ext = f".{ext}"
        return f"{stem}__{file_hash[:12]}{ext}"
