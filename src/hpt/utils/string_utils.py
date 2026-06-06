from __future__ import annotations

from collections.abc import Iterable


def to_clean_list(value: list[str] | str | None, *, lower: bool = True) -> list[str]:
    """Coerce a comma-separated string or iterable into a clean list of tokens.

    Accepts ``None`` (-> ``[]``), a comma-separated string, or an iterable of
    strings. Each token is stripped, empty tokens are dropped, and tokens are
    lowercased when ``lower`` is True. This is the single normalizer for any
    "comma-separated string OR list" input across the codebase.
    """
    if value is None:
        return []
    parts: Iterable[str] = value.split(",") if isinstance(value, str) else value
    cleaned: list[str] = []
    for part in parts:
        text = str(part).strip()
        if not text:
            continue
        cleaned.append(text.lower() if lower else text)
    return cleaned


def convert_string_to_list(string: str) -> list[str]:
    return to_clean_list(string, lower=True)
