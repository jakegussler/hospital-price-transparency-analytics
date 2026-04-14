"""Allow ``python -m hpt.ingest.download`` as an alias for ``hpt download``."""

from hpt.cli import download

if __name__ == "__main__":
    download()
