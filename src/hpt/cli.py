"""CLI entrypoints for the HPT pipeline."""

import click


@click.group()
def cli() -> None:
    """Hospital Price Transparency pipeline CLI."""


@cli.command()
@click.argument("hospital_id", required=False)
def parse(hospital_id: str | None) -> None:
    """Parse source files into bronze parquet."""
    click.echo(f"parse: not yet implemented (hospital_id={hospital_id})")


@cli.command()
@click.argument("hospital_id", required=False)
def download(hospital_id: str | None) -> None:
    """Download source MRF files."""
    click.echo(f"download: not yet implemented (hospital_id={hospital_id})")
