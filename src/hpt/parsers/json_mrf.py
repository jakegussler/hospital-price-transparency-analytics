"""Streaming parser for JSON MRF files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from hpt.parsers.base import BaseParser

if TYPE_CHECKING:
    import polars as pl


class JsonMrfParser(BaseParser):
    """Parse CMS JSON MRF files using streaming (ijson)."""

    def parse(self, file_path: Path) -> Iterator[pl.DataFrame]:
        raise NotImplementedError
