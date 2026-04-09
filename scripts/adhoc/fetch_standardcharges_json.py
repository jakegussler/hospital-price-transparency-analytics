#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_URL = (
    "https://finance.vumc.org/assets/pub/pt/"
    "352528741_vanderbilt-university-medical-center_standardcharges.json"
)


def default_output_path(url: str) -> Path:
    filename = Path(urlparse(url).path).name or "standardcharges.json"
    return Path("data") / filename


def format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def print_progress(downloaded: int, total: int | None) -> None:
    if total and total > 0:
        percent = (downloaded / total) * 100
        message = (
            f"\rDownloaded {format_bytes(downloaded)} / {format_bytes(total)} "
            f"({percent:5.1f}%)"
        )
    else:
        message = f"\rDownloaded {format_bytes(downloaded)} (total size unknown)"
    sys.stdout.write(message)
    sys.stdout.flush()


def stream_json_to_file(url: str, output_path: Path, chunk_size: int, timeout: int) -> tuple[int, int | None]:
    request = Request(
        url,
        headers={
            "User-Agent": "hospital-price-transparency/0.1 (+https://cursor.sh)",
            "Accept": "application/json",
        },
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".part")

    with urlopen(request, timeout=timeout) as response, temp_path.open("wb") as sink:
        total_header = response.headers.get("Content-Length")
        total_bytes = int(total_header) if total_header and total_header.isdigit() else None
        downloaded = 0
        report_step = 5 * 1024 * 1024
        next_report = report_step

        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            sink.write(chunk)
            downloaded += len(chunk)
            if downloaded >= next_report:
                print_progress(downloaded, total_bytes)
                next_report += report_step

    print_progress(downloaded, total_bytes)
    print()
    temp_path.replace(output_path)
    return downloaded, total_bytes


def validate_json_file(output_path: Path) -> None:
    with output_path.open("r", encoding="utf-8") as handle:
        json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a hospital standard charges JSON file and save it locally."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Source JSON URL.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to data/<filename-from-url>.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024 * 1024,
        help="Download chunk size in bytes (default: 1048576).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Socket timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--validate-json",
        action="store_true",
        help="Parse downloaded file to verify valid JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = args.output or default_output_path(args.url)
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be greater than zero.")

    downloaded, total = stream_json_to_file(
        url=args.url,
        output_path=output_path,
        chunk_size=args.chunk_size,
        timeout=args.timeout,
    )
    if args.validate_json:
        print("Validating JSON...")
        validate_json_file(output_path)
        print("JSON validation passed.")

    if total:
        print(f"Saved JSON to {output_path} ({format_bytes(downloaded)} of {format_bytes(total)})")
    else:
        print(f"Saved JSON to {output_path} ({format_bytes(downloaded)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
