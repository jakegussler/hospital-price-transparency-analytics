"""Parser for CSV tall-format MRF files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from hpt.parsers.base import BaseParser

if TYPE_CHECKING:
    import polars as pl


class CsvTallParser(BaseParser):
    """Parse CSV tall-format hospital MRF files."""

    def parse(self, file_path: Path) -> Iterator[pl.DataFrame]:
        raise NotImplementedError
