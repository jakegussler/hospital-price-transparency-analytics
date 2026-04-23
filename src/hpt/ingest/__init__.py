"""MRF acquisition and ingest-time validation utilities."""

__all__ = ["CMSMRFJson"]


def __getattr__(name: str):
    if name == "CMSMRFJson":
        from hpt.ingest.cms_json_models import CMSMRFJson

        return CMSMRFJson
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
