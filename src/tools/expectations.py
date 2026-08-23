from datetime import date as date_cls, datetime
from typing import List


def select_fiscal_year_estimate(rows: List[dict], period: str, today: date_cls) -> dict:
    if not rows:
        raise ValueError("no estimate rows")

    future = sorted(
        (r for r in rows if datetime.fromisoformat(r["date"]).date() >= today),
        key=lambda r: r["date"],
    )
    index = {"current": 0, "next": 1}.get(period)
    if index is None:
        raise ValueError(f"unknown period '{period}', expected 'current' or 'next'")
    if index >= len(future):
        raise ValueError(f"no '{period}' fiscal year estimate available")
    return future[index]


def compute_earnings_surprise_summary(quarterly_rows: List[dict]) -> dict:
    if not quarterly_rows:
        raise ValueError("no quarterly earnings rows")

    ordered = sorted(quarterly_rows, key=lambda r: r["fiscal_date_ending"], reverse=True)
    latest = ordered[0]
    last_4q = ordered[:4]
    hits = [r for r in last_4q if r.get("surprise") is not None and r["surprise"] > 0]

    return {
        "latest_surprise": latest.get("surprise"),
        "latest_surprise_percentage": latest.get("surprise_percentage"),
        "hit_rate_last_4q": len(hits) / len(last_4q) if last_4q else None,
    }
