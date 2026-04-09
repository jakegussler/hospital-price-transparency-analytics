#!/usr/bin/env python3

from __future__ import annotations

import argparse
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_URL = (
    "https://finance.vumc.org/assets/pub/pt/"
    "352528741_vanderbilt-university-medical-center_standardcharges.json"
)


def format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def get_headers(url: str, timeout: int):
    common_headers = {
        "User-Agent": "hospital-price-transparency/0.1 (+https://cursor.sh)",
        "Accept": "application/json",
    }

    head_request = Request(url, method="HEAD", headers=common_headers)
    try:
        with urlopen(head_request, timeout=timeout) as response:
            return response.headers
    except HTTPError as exc:
        if exc.code not in {400, 403, 404, 405, 501}:
            raise

    get_request = Request(url, method="GET", headers=common_headers)
    with urlopen(get_request, timeout=timeout) as response:
        return response.headers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check remote JSON file metadata, including size if available."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Source JSON URL.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Request timeout in seconds (default: 60).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headers = get_headers(args.url, args.timeout)
    content_length = headers.get("Content-Length")
    content_type = headers.get("Content-Type", "unknown")
    filename = urlparse(args.url).path.rsplit("/", 1)[-1] or "unknown"

    print(f"URL: {args.url}")
    print(f"File: {filename}")
    print(f"Content-Type: {content_type}")

    if content_length and content_length.isdigit():
        size_bytes = int(content_length)
        print(f"Content-Length: {size_bytes} bytes ({format_bytes(size_bytes)})")
    else:
        print("Content-Length: not provided by server")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
