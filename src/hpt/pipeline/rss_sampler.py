"""Peak-RSS sampling for the current process during a bounded operation.

dbt runs in-process via ``dbtRunner`` and DuckDB is embedded, so the work of a
dbt invocation lives in this process's address space. To attribute a *per-invoke*
peak (several invokes share one CLI process, so the OS high-water mark is
process-cumulative and cannot be reset), we sample resident set size on a daemon
thread for the duration of the operation and keep the maximum.

This is observability: it must never be able to fail the operation it measures.
Construction failures and sampling errors degrade to ``None`` rather than raising.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator

_BYTES_PER_MB = 1024 * 1024


class PeakRssSampler:
    """Holds the sampled memory figures for one ``peak_rss_sampler`` block."""

    def __init__(self) -> None:
        self.start_mb: float | None = None
        self.peak_mb: float | None = None

    @property
    def delta_mb(self) -> float | None:
        if self.start_mb is None or self.peak_mb is None:
            return None
        return self.peak_mb - self.start_mb


@contextlib.contextmanager
def peak_rss_sampler(interval_s: float = 0.1) -> Iterator[PeakRssSampler]:
    """Sample this process's RSS until the block exits; expose start/peak/delta MB.

    If ``psutil`` is unavailable or sampling fails, the figures stay ``None`` and
    the block still runs normally.
    """
    sampler = PeakRssSampler()
    try:
        import psutil

        process = psutil.Process()
    except Exception:  # noqa: BLE001 - never let measurement break the caller
        yield sampler
        return

    def _rss_mb() -> float:
        return process.memory_info().rss / _BYTES_PER_MB

    try:
        sampler.start_mb = sampler.peak_mb = _rss_mb()
    except Exception:  # noqa: BLE001
        yield sampler
        return

    stop = threading.Event()

    def _poll() -> None:
        while not stop.is_set():
            try:
                current = _rss_mb()
            except Exception:  # noqa: BLE001 - process may have changed under us
                break
            if sampler.peak_mb is None or current > sampler.peak_mb:
                sampler.peak_mb = current
            stop.wait(interval_s)

    thread = threading.Thread(target=_poll, name="hpt-rss-sampler", daemon=True)
    thread.start()
    try:
        yield sampler
    finally:
        stop.set()
        thread.join(timeout=interval_s * 5)
