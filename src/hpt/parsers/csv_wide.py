"""Parser for CSV wide-format MRF files (dynamic payer columns)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from hpt.parsers.base import BaseParser

if TYPE_CHECKING:
    import polars as pl


class CsvWideParser(BaseParser):
    """Parse and unpivot CSV wide-format hospital MRF files."""

    def parse(self, file_path: Path) -> Iterator[pl.DataFrame]:
        raise NotImplementedError
