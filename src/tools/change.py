from datetime import date
from typing import List, Optional


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old


def _price_at_or_before(price_rows: List[dict], since_str: str) -> Optional[dict]:
    candidates = [r for r in price_rows if r["date"] <= since_str]
    return max(candidates, key=lambda r: r["date"]) if candidates else None


def _snapshot_at_or_before(estimate_rows: List[dict], since_str: str) -> Optional[dict]:
    candidates = [r for r in estimate_rows if r["snapshot_at"][:10] <= since_str]
    return max(candidates, key=lambda r: r["snapshot_at"]) if candidates else None


def compute_change_since(price_rows: List[dict], estimate_rows: List[dict], since_date: date) -> dict:
    if not price_rows:
        raise ValueError("no price rows")

    since_str = since_date.isoformat()
    ordered_prices = sorted(price_rows, key=lambda r: r["date"])
    price_now_row = ordered_prices[-1]
    price_then_row = _price_at_or_before(ordered_prices, since_str)

    price_now = price_now_row["close"]
    price_then = price_then_row["close"] if price_then_row else None

    eps_then = eps_now = revenue_then = revenue_now = None
    if estimate_rows:
        ordered_estimates = sorted(estimate_rows, key=lambda r: r["snapshot_at"])
        est_now_row = ordered_estimates[-1]
        est_then_row = _snapshot_at_or_before(ordered_estimates, since_str)
        eps_now = est_now_row.get("eps_mean")
        revenue_now = est_now_row.get("revenue_mean")
        if est_then_row:
            eps_then = est_then_row.get("eps_mean")
            revenue_then = est_then_row.get("revenue_mean")

    return {
        "since_date": since_str,
        "price_then": price_then,
        "price_now": price_now,
        "price_change_pct": _pct_change(price_now, price_then),
        "eps_then": eps_then,
        "eps_now": eps_now,
        "eps_change_pct": _pct_change(eps_now, eps_then),
        "revenue_then": revenue_then,
        "revenue_now": revenue_now,
        "revenue_change_pct": _pct_change(revenue_now, revenue_then),
    }
