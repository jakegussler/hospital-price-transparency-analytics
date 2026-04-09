"""Abstract base parser that all format-specific parsers implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    import polars as pl


class BaseParser(ABC):
    """Contract for format-specific MRF parsers.

    Each concrete parser (JSON, CSV tall, CSV wide) implements ``parse()``
    which yields batches of rows in a uniform bronze schema regardless of
    the source format.
    """

    def __init__(self, hospital_config: dict[str, Any]) -> None:
        self.hospital_config = hospital_config
        self.hospital_id: str = hospital_config["hospital_id"]

    @abstractmethod
    def parse(self, file_path: Path) -> Iterator[pl.DataFrame]:
        """Yield DataFrames of uniform bronze rows from *file_path*."""
