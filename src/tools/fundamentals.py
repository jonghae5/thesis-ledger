from datetime import date
from typing import List, Optional


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b in (None, 0):
        return None
    return a / b


def compute_fundamentals_metrics(rows: List[dict]) -> dict:
    if not rows:
        raise ValueError("no fundamentals rows")

    ordered = sorted(rows, key=lambda r: r["period"])
    latest = ordered[-1]
    prev = ordered[-2] if len(ordered) >= 2 else None

    fcf_margin = _safe_div(latest.get("fcf"), latest.get("revenue"))
    net_debt = None
    if latest.get("debt") is not None and latest.get("cash") is not None:
        net_debt = latest["debt"] - latest["cash"]

    revenue_growth = None
    gross_margin_change = None
    share_dilution = None
    if prev:
        if latest.get("revenue") is not None and prev.get("revenue") not in (None, 0):
            revenue_growth = (latest["revenue"] - prev["revenue"]) / prev["revenue"]
        latest_margin = _safe_div(latest.get("gross_profit"), latest.get("revenue"))
        prev_margin = _safe_div(prev.get("gross_profit"), prev.get("revenue"))
        if latest_margin is not None and prev_margin is not None:
            gross_margin_change = latest_margin - prev_margin
        if latest.get("shares") is not None and prev.get("shares") not in (None, 0):
            share_dilution = latest["shares"] / prev["shares"] - 1

    return {
        "ticker": latest["ticker"],
        "period": latest["period"],
        "fcf_margin": fcf_margin,
        "net_debt": net_debt,
        "revenue_growth": revenue_growth,
        "gross_margin_change": gross_margin_change,
        "share_dilution": share_dilution,
    }


_FLOW_FIELDS = (
    "revenue", "gross_profit", "operating_income", "net_income",
    "operating_cashflow", "capex", "fcf",
)


def _merge_latest_by_period(rows: List[dict]) -> List[dict]:
    """Merge facts for one period, preferring the newest non-null disclosure."""
    merged: dict[str, dict] = {}
    for row in sorted(rows, key=lambda value: value["filed_at"], reverse=True):
        period = row["period"]
        target = merged.setdefault(period, dict(row))
        for field in _FLOW_FIELDS + ("cash", "debt", "shares"):
            if target.get(field) is None and row.get(field) is not None:
                target[field] = row[field]
    return sorted(merged.values(), key=lambda value: value["period"])


def _prior_year_row(row: dict, candidates: List[dict]) -> Optional[dict]:
    current = date.fromisoformat(row["period"])
    matches = []
    for candidate in candidates:
        days = (current - date.fromisoformat(candidate["period"])).days
        if 350 <= days <= 380:
            matches.append((abs(days - 365), candidate))
    return min(matches, key=lambda value: value[0])[1] if matches else None


def compute_ttm_fundamentals(rows: List[dict]) -> dict:
    """Derive TTM figures by replacing reported annual quarters with newer ones.

    SEC 10-Q flow facts are discrete quarters. For quarters reported after the
    latest 10-K, TTM = latest annual + current quarters - prior-year quarters.
    Missing fields stay null instead of being estimated.
    """
    if not rows:
        raise ValueError("no fundamental snapshots")

    annual = _merge_latest_by_period([
        row for row in rows if row.get("form") in {"10-K", "10-K/A", "LEGACY"}
    ])
    if not annual:
        raise ValueError("no annual filing snapshot")
    base = annual[-1]

    quarters = _merge_latest_by_period([
        row for row in rows
        if row.get("form") in {"10-Q", "10-Q/A"} and row.get("revenue") is not None
    ])
    latest_quarter = quarters[-1] if quarters else None
    replacement_quarters = [
        row for row in quarters if row["period"] > base["period"]
    ][-3:]
    replacements = [(row, _prior_year_row(row, quarters)) for row in replacement_quarters]

    ttm = {}
    for field in _FLOW_FIELDS:
        base_value = base.get(field)
        if base_value is None or any(
            current.get(field) is None or prior is None or prior.get(field) is None
            for current, prior in replacements
        ):
            ttm[field] = None
        else:
            ttm[field] = base_value + sum(
                current[field] - prior[field] for current, prior in replacements
            )

    latest_period = latest_quarter["period"] if latest_quarter else base["period"]
    balance_rows = sorted(
        [row for row in rows if row["period"] <= latest_period],
        key=lambda row: (row["period"], row["filed_at"]), reverse=True,
    )

    def latest_value(field: str):
        return next((row[field] for row in balance_rows if row.get(field) is not None), None)

    comparison = _prior_year_row(latest_quarter, quarters) if latest_quarter else None
    revenue_growth_yoy = None
    gross_margin_change_yoy = None
    if latest_quarter and comparison:
        revenue_growth_yoy = _safe_div(
            latest_quarter.get("revenue"), comparison.get("revenue"),
        )
        if revenue_growth_yoy is not None:
            revenue_growth_yoy -= 1
        current_margin = _safe_div(latest_quarter.get("gross_profit"), latest_quarter.get("revenue"))
        prior_margin = _safe_div(comparison.get("gross_profit"), comparison.get("revenue"))
        if current_margin is not None and prior_margin is not None:
            gross_margin_change_yoy = current_margin - prior_margin

    cash = latest_value("cash")
    debt = latest_value("debt")
    return {
        "ticker": base["ticker"],
        "basis": "TTM_DERIVED" if replacement_quarters else "ANNUAL_FALLBACK",
        "period": latest_period,
        "filed_at": latest_quarter["filed_at"] if latest_quarter else base["filed_at"],
        "annual_base_period": base["period"],
        "quarters_replaced": len(replacement_quarters),
        "revenue": ttm["revenue"] if replacements else base.get("revenue"),
        "gross_profit": ttm["gross_profit"] if replacements else base.get("gross_profit"),
        "operating_income": ttm["operating_income"] if replacements else base.get("operating_income"),
        "net_income": ttm["net_income"] if replacements else base.get("net_income"),
        "fcf": ttm["fcf"] if replacements else base.get("fcf"),
        "fcf_margin": _safe_div(
            ttm["fcf"] if replacements else base.get("fcf"),
            ttm["revenue"] if replacements else base.get("revenue"),
        ),
        "revenue_growth_yoy": revenue_growth_yoy,
        "gross_margin_change_yoy": gross_margin_change_yoy,
        "cash": cash,
        "debt": debt,
        "net_debt": debt - cash if debt is not None and cash is not None else None,
        "shares": latest_value("shares"),
        "source_type": "MODEL_OUTPUT",
    }
