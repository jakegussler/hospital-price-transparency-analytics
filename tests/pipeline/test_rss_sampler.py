"""Tests for hpt.pipeline.rss_sampler."""

from __future__ import annotations

import builtins

import pytest

from hpt.pipeline.rss_sampler import peak_rss_sampler


def test_sampler_reports_positive_memory() -> None:
    with peak_rss_sampler(interval_s=0.01) as sampler:
        # Allocate something so peak is at least start.
        _ = [0] * 100_000
    assert sampler.start_mb is not None
    assert sampler.peak_mb is not None
    assert sampler.peak_mb >= sampler.start_mb
    assert sampler.delta_mb is not None


def test_sampler_degrades_to_none_without_psutil(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def _no_psutil(name: str, *args: object, **kwargs: object) -> object:
        if name == "psutil":
            raise ImportError("psutil unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_psutil)

    with peak_rss_sampler() as sampler:
        pass

    # No dependency, no crash: figures are simply absent.
    assert sampler.peak_mb is None
    assert sampler.start_mb is None
    assert sampler.delta_mb is None
