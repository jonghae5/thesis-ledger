#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.27",
#   "markitdown[pdf]>=0.1.3",
# ]
# ///

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import httpx
from markitdown import MarkItDown


BASE_URL = "https://consensus.hankyung.com"
USER_AGENT = "ThesisLedger/0.1 (+personal, low-frequency research)"
MAX_PDF_BYTES = 50 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download one Hankyung Consensus PDF temporarily and convert it to Markdown."
    )
    parser.add_argument("--report-idx", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def download_pdf(report_idx: int, destination: Path) -> int:
    if report_idx <= 0:
        raise ValueError("report-idx must be positive")
    url = f"{BASE_URL}/analysis/downpdf?report_idx={report_idx}"
    total = 0
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            declared_size = response.headers.get("content-length")
            if declared_size and int(declared_size) > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds the 50 MiB safety limit")
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_PDF_BYTES:
                        raise ValueError("PDF exceeds the 50 MiB safety limit")
                    handle.write(chunk)

    if total == 0 or not destination.read_bytes()[:5].startswith(b"%PDF-"):
        raise ValueError("downloaded content is not a PDF")
    return total


def main() -> int:
    args = parse_args()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="thesis-hankyung-") as temp_dir:
            pdf_path = Path(temp_dir) / f"{args.report_idx}.pdf"
            pdf_bytes = download_pdf(args.report_idx, pdf_path)
            result = MarkItDown(enable_plugins=False).convert(pdf_path)
            markdown = result.text_content.strip()
            if not markdown:
                raise ValueError("MarkItDown returned empty text")
            args.output.write_text(markdown + "\n", encoding="utf-8")

        print(
            json.dumps(
                {
                    "status": "OK",
                    "report_idx": args.report_idx,
                    "source_url": f"{BASE_URL}/analysis/downpdf?report_idx={args.report_idx}",
                    "pdf_bytes": pdf_bytes,
                    "markdown_chars": len(markdown),
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    except (ValueError, OSError, httpx.HTTPError) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error": str(exc)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
