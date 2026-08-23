from datetime import date, datetime, timezone
from typing import Optional

from src.storage import repository
from src.tools.business_quality import compute_business_quality_inputs
from src.tools.change import compute_change_since
from src.tools.dcf import implied_growth_rate
from src.tools.fundamentals import compute_fundamentals_metrics, compute_ttm_fundamentals
from src.tools.market import compute_market_metrics
from src.tools.macro import build_macro_context
from src.tools.revisions import compute_revision_metrics
from src.tools.valuation import compute_forward_multiples


DEFAULT_MAX_PRICE_AGE_DAYS = 7


def require_fresh_price(rows: list[dict], ticker: str, max_age_days: int) -> dict:
    if max_age_days < 0:
        raise ValueError("max_price_age_days must be non-negative")
    if not rows:
        raise ValueError(f"no stored price for {ticker} - run 'data fetch' first")
    latest = rows[0]
    price_date = date.fromisoformat(latest["date"])
    age_days = (date.today() - price_date).days
    if age_days < 0:
        raise ValueError(f"stored price for {ticker} is future-dated: {latest['date']}")
    if age_days > max_age_days:
        raise ValueError(
            f"stored price for {ticker} is stale ({latest['date']}, {age_days} days old); "
            "run 'data fetch'"
        )
    return latest


def latest_price_record(con, ticker: str, max_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    return require_fresh_price(repository.get_latest_prices(con, ticker, limit=1), ticker, max_age_days)


def resolve_estimate_period(rows: list[dict], requested: Optional[str] = None) -> str:
    periods = sorted({row["fiscal_period"] for row in rows if row.get("fiscal_period")})
    if requested is not None:
        if requested not in periods:
            raise ValueError(f"no estimate snapshots for fiscal period {requested}")
        return requested
    today = date.today().isoformat()
    future = [period for period in periods if period >= today]
    if future:
        return future[0]
    if periods:
        return periods[-1]
    raise ValueError("estimate snapshots have no fiscal_period")


def latest_fundamentals_row(con, ticker: str, as_of: Optional[date] = None) -> dict:
    effective_date = as_of or date.today()
    rows = repository.get_annual_fundamentals_as_of(con, ticker, effective_date, limit=1)
    if not rows:
        raise ValueError(
            f"no point-in-time fundamentals for {ticker} as of {effective_date} - "
            "run 'data fetch' first"
        )
    return rows[0]


def market_payload(con, ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    rows = repository.get_latest_prices(con, ticker, limit=400)
    latest = require_fresh_price(rows, ticker, max_price_age_days)
    return {
        **compute_market_metrics(ticker, rows),
        "as_of_date": latest["date"],
        "provenance": {
            "source": latest.get("source"),
            "source_url": latest.get("source_url"),
            "retrieved_at": latest.get("retrieved_at"),
        },
    }


def fundamentals_payload(con, ticker: str, as_of: Optional[date] = None) -> dict:
    effective_date = as_of or date.today()
    rows = repository.get_annual_fundamentals_as_of(con, ticker, effective_date, limit=8)
    if not rows:
        raise ValueError("no stored fundamentals - run 'data fetch' first")
    snapshots = repository.get_fundamental_snapshots_as_of(con, ticker, effective_date)
    ttm = compute_ttm_fundamentals(snapshots)
    return {
        **compute_fundamentals_metrics(rows),
        "ttm": ttm,
        "as_of_date": effective_date.isoformat(),
        "data_filed_at": rows[0]["reported_at"],
        "currency": rows[0].get("currency"),
        "source_type": "MODEL_OUTPUT",
        "provenance": {
            "source": rows[0].get("source"),
            "source_url": rows[0].get("source_url"),
            "retrieved_at": rows[0].get("retrieved_at"),
        },
    }


def business_quality_payload(con, ticker: str, as_of: Optional[date] = None) -> dict:
    effective_date = as_of or date.today()
    rows = repository.get_annual_fundamentals_as_of(con, ticker, effective_date, limit=10)
    if not rows:
        raise ValueError("no stored fundamentals - run 'data fetch' first")
    return {
        **compute_business_quality_inputs(rows),
        "as_of_date": effective_date.isoformat(),
        "data_filed_at": rows[0]["reported_at"],
        "currency": rows[0].get("currency"),
        "provenance": {
            "source": rows[0].get("source"),
            "source_url": rows[0].get("source_url"),
            "retrieved_at": rows[0].get("retrieved_at"),
        },
    }


def valuation_fundamentals_row(con, ticker: str, as_of: Optional[date] = None) -> dict:
    """Prefer a complete TTM row, otherwise preserve the annual valuation basis."""
    effective_date = as_of or date.today()
    annual = latest_fundamentals_row(con, ticker, effective_date)
    snapshots = repository.get_fundamental_snapshots_as_of(con, ticker, effective_date)
    ttm = compute_ttm_fundamentals(snapshots)
    required = ("revenue", "fcf", "net_income")
    if all(ttm.get(field) is not None for field in required):
        return {
            **annual,
            **{field: ttm.get(field) for field in required},
            "cash": ttm.get("cash"), "debt": ttm.get("debt"),
            "shares": ttm.get("shares"), "period": ttm["period"],
            "reported_at": ttm["filed_at"],
            "financial_basis": ttm["basis"],
        }
    return {**annual, "financial_basis": "ANNUAL_FALLBACK"}


def expectations_payload(con, ticker: str, fiscal_period: Optional[str] = None) -> dict:
    rows = repository.get_estimate_snapshots(con, ticker, limit=200)
    if not rows:
        raise ValueError("no stored consensus - run 'data expectations' first")
    resolved_period = resolve_estimate_period(rows, fiscal_period)
    latest = repository.get_estimate_snapshots(
        con, ticker, limit=1, fiscal_period=resolved_period,
    )[0]
    return {
        "ticker": ticker,
        "fiscal_period": resolved_period,
        "snapshot_at": latest["snapshot_at"],
        "source_type": "ESTIMATE",
        "provenance": {
            "source": latest.get("source"),
            "source_url": latest.get("source_url"),
            "retrieved_at": latest.get("retrieved_at"),
        },
        "eps": {
            "mean": latest["eps_mean"], "high": latest["eps_high"],
            "low": latest["eps_low"], "analyst_count": latest["analyst_count"],
        },
        "revenue": {
            "mean": latest["revenue_mean"], "high": latest["revenue_high"],
            "low": latest["revenue_low"],
        },
    }


def revisions_payload(con, ticker: str, fiscal_period: Optional[str] = None) -> dict:
    all_snapshots = repository.get_estimate_snapshots(con, ticker, limit=200)
    if not all_snapshots:
        raise ValueError("no estimate history - run 'data expectations' on different days")
    resolved_period = resolve_estimate_period(all_snapshots, fiscal_period)
    snapshots = repository.get_estimate_snapshots(
        con, ticker, limit=200, fiscal_period=resolved_period,
    )
    return {
        "ticker": ticker,
        **compute_revision_metrics(snapshots, now=datetime.now(timezone.utc)),
    }


def macro_payload(con, as_of: Optional[date] = None) -> dict:
    return build_macro_context(repository.get_latest_macro_snapshots(con, as_of=as_of), as_of=as_of)


def valuation_payload(con, ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    price_record = latest_price_record(con, ticker, max_price_age_days)
    fundamentals = valuation_fundamentals_row(con, ticker)
    estimate_rows = repository.get_estimate_snapshots(con, ticker, limit=200)
    estimate = None
    estimate_period = None
    if estimate_rows:
        estimate_period = resolve_estimate_period(estimate_rows)
        estimate = repository.get_estimate_snapshots(
            con, ticker, limit=1, fiscal_period=estimate_period,
        )[0]
    metrics = compute_forward_multiples(price_record["close"], fundamentals, estimate)
    return {
        "ticker": ticker,
        "price": price_record["close"],
        "price_as_of_date": price_record["date"],
        "fundamentals_filed_at": fundamentals.get("reported_at"),
        "financial_basis": fundamentals.get("financial_basis"),
        "forward_fiscal_period": estimate_period,
        "source_type": "MODEL_OUTPUT",
        **metrics,
    }


def reverse_dcf_payload(
    con,
    ticker: str,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
) -> dict:
    price_record = latest_price_record(con, ticker, max_price_age_days)
    fundamentals = valuation_fundamentals_row(con, ticker)
    shares = fundamentals.get("shares")
    revenue = fundamentals.get("revenue")
    fcf = fundamentals.get("fcf")
    debt = fundamentals.get("debt")
    cash = fundamentals.get("cash")
    if not shares or not revenue or fcf is None or debt is None or cash is None:
        raise ValueError("fundamentals row missing shares/revenue/fcf/debt/cash")
    fcf_margin = fcf / revenue
    enterprise_value = price_record["close"] * shares + debt - cash
    growth = implied_growth_rate(
        revenue, fcf_margin, enterprise_value, discount_rate, terminal_growth, years,
    )
    return {
        "ticker": ticker,
        "price": price_record["close"],
        "price_as_of_date": price_record["date"],
        "fundamentals_filed_at": fundamentals.get("reported_at"),
        "financial_basis": fundamentals.get("financial_basis"),
        "enterprise_value": enterprise_value,
        "implied_revenue_cagr": growth,
        "fcf_margin_assumed": fcf_margin,
        "discount_rate": discount_rate,
        "terminal_growth": terminal_growth,
        "years": years,
        "source_type": "MODEL_OUTPUT",
    }
