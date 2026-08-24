#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "beautifulsoup4>=4.12",
#   "httpx>=0.27",
# ]
# ///

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://consensus.hankyung.com"
LIST_URL = f"{BASE_URL}/analysis/list"
USER_AGENT = "ThesisLedger/0.1 (+personal, low-frequency research)"
REPORT_INDEX_RE = re.compile(r"^\d+$")
STOCK_CODE_RE = re.compile(r"\((\d{6})\)")


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(
        description="List Korean broker reports from Hankyung Consensus as JSON."
    )
    parser.add_argument("--sdate", default=(today - timedelta(days=30)).isoformat())
    parser.add_argument("--edate", default=today.isoformat())
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--ticker", help="Exact six-digit Korean stock code")
    parser.add_argument("--query", help="Case-insensitive title substring")
    parser.add_argument("--max-results", type=int, default=100)
    return parser.parse_args()


def normalized_date(value: str) -> str:
    return date.fromisoformat(value).isoformat()


def extract_report_idx(href: str) -> int | None:
    parsed = urlparse(href)
    if parsed.path != "/analysis/downpdf":
        return None
    values = parse_qs(parsed.query).get("report_idx", [])
    if len(values) != 1 or not REPORT_INDEX_RE.fullmatch(values[0]):
        return None
    return int(values[0])


def parse_target_price(raw: str) -> int | None:
    compact = raw.replace(",", "").replace("원", "").strip()
    return int(compact) if compact.isdigit() else None


def parse_reports(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    reports: list[dict[str, Any]] = []

    for row in soup.select(".table_style01 table tbody tr"):
        cells = row.select("td")
        if len(cells) < 6:
            continue
        anchor = row.select_one("td.text_l a[href*='/analysis/downpdf?report_idx=']")
        if anchor is None:
            continue

        href = str(anchor.get("href") or "")
        report_idx = extract_report_idx(href)
        if report_idx is None:
            continue

        title = anchor.get_text(" ", strip=True)
        stock_match = STOCK_CODE_RE.search(title)
        stock_code = stock_match.group(1) if stock_match else None
        company = title[: stock_match.start()].strip() if stock_match else None
        target_price = cells[2].get_text(" ", strip=True)

        reports.append(
            {
                "report_idx": report_idx,
                "date": cells[0].get_text(" ", strip=True),
                "company": company,
                "stock_code": stock_code,
                "title": title,
                "target_price": target_price or None,
                "target_price_krw": parse_target_price(target_price),
                "opinion": cells[3].get_text(" ", strip=True) or None,
                "analyst": cells[4].get_text(" ", strip=True) or None,
                "broker": cells[5].get_text(" ", strip=True) or None,
                "pdf_url": urljoin(BASE_URL, href),
            }
        )

    return reports


def main() -> int:
    args = parse_args()
    try:
        sdate = normalized_date(args.sdate)
        edate = normalized_date(args.edate)
        if sdate > edate:
            raise ValueError("sdate must be on or before edate")
        if not 1 <= args.pages <= 10:
            raise ValueError("pages must be between 1 and 10")
        if not 1 <= args.max_results <= 500:
            raise ValueError("max-results must be between 1 and 500")
        if args.ticker and not re.fullmatch(r"\d{6}", args.ticker):
            raise ValueError("ticker must be a six-digit Korean stock code")

        collected: list[dict[str, Any]] = []
        seen: set[int] = set()
        with httpx.Client(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20.0
        ) as client:
            for page in range(1, args.pages + 1):
                params = {
                    "skinType": "business",
                    "sdate": sdate,
                    "edate": edate,
                    "now_page": page,
                }
                server_query = args.ticker or args.query
                if server_query:
                    params.update(
                        {"search_value": "REPORT_TITLE", "search_text": server_query}
                    )
                response = client.get(
                    LIST_URL,
                    params=params,
                )
                response.raise_for_status()
                page_reports = parse_reports(response.text)
                if not page_reports:
                    break

                for report in page_reports:
                    report_idx = report["report_idx"]
                    if report_idx in seen:
                        continue
                    seen.add(report_idx)
                    if args.ticker and report["stock_code"] != args.ticker:
                        continue
                    if args.query and args.query.casefold() not in report["title"].casefold():
                        continue
                    collected.append(report)
                    if len(collected) >= args.max_results:
                        break

                if len(collected) >= args.max_results:
                    break
                if page < args.pages:
                    time.sleep(0.5)

        print(
            json.dumps(
                {
                    "status": "OK",
                    "source": LIST_URL,
                    "sdate": sdate,
                    "edate": edate,
                    "count": len(collected),
                    "reports": collected,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    except (ValueError, httpx.HTTPError) as exc:
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
