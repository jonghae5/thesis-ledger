from datetime import date
from statistics import median, pstdev
from typing import Callable, Optional


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _positive_denominator_ratio(
    numerator: Optional[float], denominator: Optional[float],
) -> Optional[float]:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _series_summary(history: list[dict], field: str) -> dict:
    observations = [
        (row["period"], row["model_outputs"].get(field))
        for row in history
        if row["model_outputs"].get(field) is not None
    ]
    values = [value for _, value in observations]
    return {
        "latest": values[-1] if values else None,
        "latest_period": observations[-1][0] if observations else None,
        "median": median(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "range": max(values) - min(values) if values else None,
        "standard_deviation": pstdev(values) if len(values) >= 2 else None,
        "observations": len(values),
    }


def _annualized_change(
    rows: list[dict], getter: Callable[[dict], Optional[float]],
) -> dict:
    observations = [(row["period"], getter(row)) for row in rows]
    observations = [(period, value) for period, value in observations if value is not None and value > 0]
    if len(observations) < 2:
        return {
            "value": None, "start_period": None, "end_period": None,
            "years": None, "observations": len(observations),
        }
    start_period, start_value = observations[0]
    end_period, end_value = observations[-1]
    try:
        years = (date.fromisoformat(end_period) - date.fromisoformat(start_period)).days / 365.2425
    except ValueError:
        years = 0
    value = (end_value / start_value) ** (1 / years) - 1 if years > 0 else None
    return {
        "value": value,
        "start_period": start_period,
        "end_period": end_period,
        "years": years if years > 0 else None,
        "observations": len(observations),
    }


def _cumulative_conversion(rows: list[dict], numerator: str) -> dict:
    comparable = [
        row for row in rows
        if row.get(numerator) is not None and row.get("net_income") is not None
    ]
    denominator = sum(row["net_income"] for row in comparable)
    value = None
    if comparable and denominator > 0:
        value = sum(row[numerator] for row in comparable) / denominator
    return {"value": value, "periods": len(comparable)}


def compute_business_quality_inputs(rows: list[dict]) -> dict:
    """Build score-free, deterministic inputs for qualitative business analysis."""
    if not rows:
        raise ValueError("no fundamentals rows")

    ordered = sorted(rows, key=lambda row: row["period"])
    history = []
    for row in ordered:
        revenue = row.get("revenue")
        cash = row.get("cash")
        debt = row.get("debt")
        fcf = row.get("fcf")
        net_debt = debt - cash if debt is not None and cash is not None else None
        history.append({
            "period": row["period"],
            "filed_at": row.get("reported_at") or row.get("filed_at"),
            "facts": {
                "source_type": "FACT",
                "revenue": revenue,
                "operating_cashflow": row.get("operating_cashflow"),
                "fcf": fcf,
                "cash": cash,
                "debt": debt,
                "shares": row.get("shares"),
            },
            "model_outputs": {
                "source_type": "MODEL_OUTPUT",
                "gross_margin": _safe_div(row.get("gross_profit"), revenue),
                "operating_margin": _safe_div(row.get("operating_income"), revenue),
                "net_margin": _safe_div(row.get("net_income"), revenue),
                "operating_cashflow_margin": _safe_div(row.get("operating_cashflow"), revenue),
                "fcf_margin": _safe_div(fcf, revenue),
                "capex_intensity": _safe_div(row.get("capex"), revenue),
                "operating_cashflow_to_net_income": _positive_denominator_ratio(
                    row.get("operating_cashflow"), row.get("net_income"),
                ),
                "fcf_to_net_income": _positive_denominator_ratio(fcf, row.get("net_income")),
                "net_debt": net_debt,
                "net_debt_to_fcf": _positive_denominator_ratio(net_debt, fcf),
            },
        })

    revenue_cagr = _annualized_change(ordered, lambda row: row.get("revenue"))
    shares_cagr = _annualized_change(ordered, lambda row: row.get("shares"))
    first = ordered[0]
    latest = ordered[-1]
    revenue_change = None
    operating_income_change = None
    if first.get("revenue") is not None and latest.get("revenue") is not None:
        revenue_change = latest["revenue"] - first["revenue"]
    if first.get("operating_income") is not None and latest.get("operating_income") is not None:
        operating_income_change = latest["operating_income"] - first["operating_income"]
    incremental_operating_margin = None
    if revenue_change is not None and revenue_change > 0 and operating_income_change is not None:
        incremental_operating_margin = operating_income_change / revenue_change

    warnings = []
    if len(ordered) < 3:
        warnings.append("fewer than three annual periods; durability and stability are weakly supported")
    for field in ("gross_margin", "operating_margin", "fcf_margin"):
        if _series_summary(history, field)["observations"] < 2:
            warnings.append(f"{field} has fewer than two comparable observations")

    return {
        "ticker": latest["ticker"],
        "history": history,
        "profitability": {
            "gross_margin": _series_summary(history, "gross_margin"),
            "operating_margin": _series_summary(history, "operating_margin"),
            "net_margin": _series_summary(history, "net_margin"),
        },
        "growth_and_reinvestment": {
            "revenue_cagr": revenue_cagr,
            "incremental_operating_margin": incremental_operating_margin,
            "capex_intensity": _series_summary(history, "capex_intensity"),
        },
        "cash_generation": {
            "operating_cashflow_margin": _series_summary(history, "operating_cashflow_margin"),
            "fcf_margin": _series_summary(history, "fcf_margin"),
            "operating_cashflow_to_net_income": _series_summary(
                history, "operating_cashflow_to_net_income",
            ),
            "fcf_to_net_income": _series_summary(history, "fcf_to_net_income"),
            "cumulative_operating_cashflow_to_net_income": _cumulative_conversion(
                ordered, "operating_cashflow",
            ),
            "cumulative_fcf_to_net_income": _cumulative_conversion(ordered, "fcf"),
        },
        "shareholder_and_balance_sheet": {
            "shares_cagr": shares_cagr,
            "net_debt": _series_summary(history, "net_debt"),
            "net_debt_to_fcf": _series_summary(history, "net_debt_to_fcf"),
        },
        "coverage": {
            "annual_periods": len(ordered),
            "history_start": ordered[0]["period"],
            "history_end": ordered[-1]["period"],
            "warnings": warnings,
            "unavailable_dimensions": [
                "ROIC and incremental ROIC: invested-capital and tax inputs are not stored",
                "SBC burden and net buybacks: cash repurchases and SBC are not stored",
                "working-capital quality: receivables and inventory are not stored",
                "M&A dependence: acquisition cash flows and goodwill are not stored",
            ],
        },
        "source_type": "MODEL_OUTPUT",
    }
