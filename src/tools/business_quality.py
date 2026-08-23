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


def _reported_debt(row: dict) -> Optional[float]:
    noncurrent = row.get("debt")
    current = row.get("current_debt")
    if noncurrent is None and current is None:
        return None
    return (noncurrent or 0) + (current or 0)


def _reported_tax_rate(row: dict) -> Optional[float]:
    pretax_income = row.get("pretax_income")
    tax_expense = row.get("income_tax_expense")
    if pretax_income is None or pretax_income <= 0 or tax_expense is None:
        return None
    return tax_expense / pretax_income


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
        debt = _reported_debt(row)
        fcf = row.get("fcf")
        net_debt = debt - cash if debt is not None and cash is not None else None
        tax_rate = _reported_tax_rate(row)
        usable_tax_rate = tax_rate if tax_rate is not None and 0 <= tax_rate <= 1 else None
        nopat = (
            row["operating_income"] * (1 - usable_tax_rate)
            if row.get("operating_income") is not None and usable_tax_rate is not None
            else None
        )
        invested_capital = None
        if (
            row.get("stockholders_equity") is not None
            and debt is not None
            and cash is not None
        ):
            invested_capital = (
                row["stockholders_equity"] + debt - cash
                - (row.get("short_term_investments") or 0)
            )
        working_capital = None
        if all(row.get(field) is not None for field in (
            "accounts_receivable", "inventory", "accounts_payable",
        )):
            working_capital = (
                row["accounts_receivable"] + row["inventory"] - row["accounts_payable"]
            )
        history.append({
            "period": row["period"],
            "filed_at": row.get("reported_at") or row.get("filed_at"),
            "facts": {
                "source_type": "FACT",
                "revenue": revenue,
                "operating_cashflow": row.get("operating_cashflow"),
                "fcf": fcf,
                "cash": cash,
                "debt": row.get("debt"),
                "current_debt": row.get("current_debt"),
                "shares": row.get("shares"),
                "assets": row.get("assets"),
                "stockholders_equity": row.get("stockholders_equity"),
                "short_term_investments": row.get("short_term_investments"),
                "pretax_income": row.get("pretax_income"),
                "income_tax_expense": row.get("income_tax_expense"),
                "sbc": row.get("sbc"),
                "share_repurchases": row.get("share_repurchases"),
                "accounts_receivable": row.get("accounts_receivable"),
                "inventory": row.get("inventory"),
                "accounts_payable": row.get("accounts_payable"),
                "goodwill": row.get("goodwill"),
                "acquisition_cash_paid": row.get("acquisition_cash_paid"),
                "interest_expense": row.get("interest_expense"),
            },
            "source_concepts": row.get("source_concepts", {}),
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
                "reported_debt": debt,
                "net_debt": net_debt,
                "net_debt_to_fcf": _positive_denominator_ratio(net_debt, fcf),
                "effective_tax_rate": tax_rate,
                "nopat": nopat,
                "invested_capital": invested_capital,
                "roic": None,
                "sbc_to_revenue": _positive_denominator_ratio(row.get("sbc"), revenue),
                "sbc_to_fcf": _positive_denominator_ratio(row.get("sbc"), fcf),
                "repurchases_to_sbc": _positive_denominator_ratio(
                    row.get("share_repurchases"), row.get("sbc"),
                ),
                "receivables_to_revenue": _positive_denominator_ratio(
                    row.get("accounts_receivable"), revenue,
                ),
                "inventory_to_revenue": _positive_denominator_ratio(
                    row.get("inventory"), revenue,
                ),
                "working_capital": working_capital,
                "working_capital_to_revenue": _safe_div(working_capital, revenue),
                "goodwill_to_assets": _positive_denominator_ratio(
                    row.get("goodwill"), row.get("assets"),
                ),
                "acquisition_cash_paid_to_revenue": _positive_denominator_ratio(
                    row.get("acquisition_cash_paid"), revenue,
                ),
                "interest_coverage": _positive_denominator_ratio(
                    row.get("operating_income"), row.get("interest_expense"),
                ),
            },
        })

    for index, item in enumerate(history):
        capital = item["model_outputs"].get("invested_capital")
        prior_capital = (
            history[index - 1]["model_outputs"].get("invested_capital")
            if index > 0 else None
        )
        nopat = item["model_outputs"].get("nopat")
        if capital is not None and prior_capital is not None and capital + prior_capital > 0:
            item["model_outputs"]["roic"] = nopat / ((capital + prior_capital) / 2) if nopat is not None else None

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
    invalid_tax_periods = [
        item["period"] for item in history
        if item["model_outputs"].get("effective_tax_rate") is not None
        and not 0 <= item["model_outputs"]["effective_tax_rate"] <= 1
    ]
    if invalid_tax_periods:
        warnings.append(
            "reported effective tax rate is outside 0%-100%; NOPAT and ROIC are omitted for: "
            + ", ".join(invalid_tax_periods)
        )

    availability_fields = [
        "roic", "sbc_to_revenue", "repurchases_to_sbc",
        "receivables_to_revenue", "inventory_to_revenue",
        "working_capital_to_revenue", "goodwill_to_assets",
        "acquisition_cash_paid_to_revenue", "interest_coverage",
    ]
    metric_availability = {
        field: (
            "AVAILABLE" if _series_summary(history, field)["observations"] else "MISSING"
        )
        for field in availability_fields
    }

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
        "returns_on_capital": {
            "definition": (
                "NOPAT uses reported effective tax rates from 0%-100%; invested capital is "
                "stockholders equity plus reported debt components less cash and any reported "
                "short-term investments"
            ),
            "effective_tax_rate": _series_summary(history, "effective_tax_rate"),
            "nopat": _series_summary(history, "nopat"),
            "invested_capital": _series_summary(history, "invested_capital"),
            "roic": _series_summary(history, "roic"),
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
            "interest_coverage": _series_summary(history, "interest_coverage"),
        },
        "capital_allocation": {
            "sbc_to_revenue": _series_summary(history, "sbc_to_revenue"),
            "sbc_to_fcf": _series_summary(history, "sbc_to_fcf"),
            "repurchases_to_sbc": _series_summary(history, "repurchases_to_sbc"),
        },
        "working_capital": {
            "receivables_to_revenue": _series_summary(history, "receivables_to_revenue"),
            "inventory_to_revenue": _series_summary(history, "inventory_to_revenue"),
            "working_capital": _series_summary(history, "working_capital"),
            "working_capital_to_revenue": _series_summary(
                history, "working_capital_to_revenue",
            ),
        },
        "ma_dependence": {
            "goodwill_to_assets": _series_summary(history, "goodwill_to_assets"),
            "acquisition_cash_paid_to_revenue": _series_summary(
                history, "acquisition_cash_paid_to_revenue",
            ),
        },
        "coverage": {
            "annual_periods": len(ordered),
            "history_start": ordered[0]["period"],
            "history_end": ordered[-1]["period"],
            "warnings": warnings,
            "metric_availability": metric_availability,
            "unavailable_dimensions": [
                "product/geographic segment economics: dimensional filing facts are not stored",
                "debt maturity profile: maturity footnote facts are not stored",
            ],
        },
        "source_type": "MODEL_OUTPUT",
    }
