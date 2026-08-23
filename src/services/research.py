from datetime import date, datetime, timezone
from typing import Optional

from src.storage import repository
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


def _section(builder) -> dict:
    try:
        return {"status": "OK", **builder()}
    except ValueError as exc:
        return {"status": "MISSING", "message": str(exc)}


def _guidance_section(con, ticker: str) -> dict:
    guidance = repository.get_latest_guidance_snapshot(con, ticker)
    if not guidance:
        return {"status": "MISSING", "message": "no stored management guidance"}
    source_date = guidance["source_date"]
    if isinstance(source_date, str):
        source_date = date.fromisoformat(source_date)
    age_days = (date.today() - source_date).days
    section = {"status": "OK", **guidance, "age_days": age_days}
    if age_days > 120:
        section["status"] = "STALE"
        section["message"] = f"management guidance is {age_days} days old"
    return section


def _expectation_anchors(sections: dict) -> list[str]:
    anchors = []
    has_fresh_consensus = sections["expectations"]["status"] == "OK"
    has_revision_signal = (
        sections["revisions"]["status"] == "OK"
        and sections["revisions"].get("revision_score") is not None
    )
    if has_fresh_consensus and has_revision_signal:
        anchors.append("CONSENSUS_REVISION")

    guidance = sections["guidance"]
    guidance_dimensions = (
        guidance.get("fiscal_period"), guidance.get("guidance_scope"),
        guidance.get("currency"), guidance.get("value_unit"),
    )
    has_guided_metric = any(
        guidance.get(field) is not None
        for field in ("revenue_low", "revenue_high", "margin_guidance", "capex_guidance")
    )
    if (
        guidance["status"] == "OK"
        and all(value is not None for value in guidance_dimensions)
        and has_guided_metric
        and sections["implied_expectations"]["status"] == "OK"
    ):
        anchors.append("GUIDANCE_VS_PRICE_IMPLIED")
    return anchors


def _expectations_section(con, ticker: str) -> dict:
    section = _section(lambda: expectations_payload(con, ticker))
    if section["status"] != "OK":
        return section
    snapshot_at = datetime.fromisoformat(section["snapshot_at"])
    # DuckDB TIMESTAMP returns a timezone-naive local wall time even when an
    # aware datetime was inserted. Freshness is day-based, so compare calendar
    # dates and never report a negative age because of that conversion.
    age_days = max(0, (date.today() - snapshot_at.date()).days)
    section["age_days"] = age_days
    if age_days > 2:
        section["status"] = "STALE"
        section["message"] = (
            f"consensus snapshot is {age_days} days old - run 'data expectations'"
        )
    return section


def _quality_report(sections: dict) -> dict:
    missing = [name for name, section in sections.items() if section["status"] != "OK"]
    research_core = ("market", "fundamentals", "valuation")
    can_research = all(sections[name]["status"] == "OK" for name in research_core)
    expectation_anchors = _expectation_anchors(sections)
    can_decide = can_research and bool(expectation_anchors)
    cannot_conclude = []
    warnings = []

    if sections["expectations"]["status"] != "OK":
        cannot_conclude.extend(["forward valuation", "consensus gap"])
    if sections["revisions"]["status"] != "OK" or sections["revisions"].get("revision_score") is None:
        cannot_conclude.append("consensus revision trend")
    if sections["implied_expectations"]["status"] != "OK":
        cannot_conclude.append("price-implied growth")
    if sections["macro"]["status"] != "OK":
        cannot_conclude.append("macro-sensitive scenario calibration")
        warnings.extend(sections["macro"].get("warnings", []))
    if sections["catalysts"]["status"] != "OK" or not sections["catalysts"].get("items"):
        warnings.append("no stored catalysts; upcoming event coverage may be incomplete")
    if sections["guidance"]["status"] != "OK":
        warnings.append("no stored management guidance")

    fundamentals = sections["fundamentals"]
    if fundamentals["status"] == "OK":
        for field in ("fcf_margin", "revenue_growth", "net_debt"):
            if fundamentals.get(field) is None:
                warnings.append(f"fundamentals.{field} is unavailable")

    if not can_research:
        completeness = "INSUFFICIENT"
    elif can_decide and not missing and not cannot_conclude:
        completeness = "COMPLETE"
    else:
        completeness = "PARTIAL"
    return {
        "completeness": completeness,
        "can_research": can_research,
        "can_decide": can_decide,
        "expectation_anchors": expectation_anchors,
        "missing": missing,
        "cannot_conclude": sorted(set(cannot_conclude)),
        "warnings": warnings,
    }


def build_evidence(con, ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    ticker = ticker.upper()
    sections = {
        "market": _section(lambda: market_payload(con, ticker, max_price_age_days)),
        "fundamentals": _section(lambda: fundamentals_payload(con, ticker)),
        "expectations": _expectations_section(con, ticker),
        "revisions": _section(lambda: revisions_payload(con, ticker)),
        "valuation": _section(lambda: valuation_payload(con, ticker, max_price_age_days)),
        "implied_expectations": _section(
            lambda: reverse_dcf_payload(con, ticker, max_price_age_days=max_price_age_days)
        ),
        "macro": macro_payload(con),
        "guidance": _guidance_section(con, ticker),
        "catalysts": {
            "status": "OK",
            "items": repository.get_catalysts(con, ticker, since=date.today()),
        },
    }
    return {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality": _quality_report(sections),
        "sections": sections,
    }


def compare_evidence(evidence_items: list[dict]) -> dict:
    if len(evidence_items) < 2:
        raise ValueError("compare requires at least two tickers")
    rows = []
    price_dates = set()
    filing_dates = set()
    currencies = set()
    for evidence in evidence_items:
        sections = evidence["sections"]
        market = sections["market"]
        fundamentals = sections["fundamentals"]
        expectations = sections["expectations"]
        revisions = sections["revisions"]
        valuation = sections["valuation"]
        implied = sections["implied_expectations"]
        price_dates.add(market.get("as_of_date"))
        filing_dates.add(fundamentals.get("data_filed_at"))
        currencies.add(fundamentals.get("currency"))
        rows.append({
            "ticker": evidence["ticker"],
            "completeness": evidence["quality"]["completeness"],
            "price": market.get("price"),
            "price_as_of_date": market.get("as_of_date"),
            "momentum_3m": market.get("momentum_3m"),
            "volatility_60d": market.get("volatility_60d"),
            "revenue_growth": fundamentals.get("revenue_growth"),
            "quarterly_revenue_growth_yoy": fundamentals.get("ttm", {}).get("revenue_growth_yoy"),
            "fcf_margin": fundamentals.get("fcf_margin"),
            "ttm_fcf_margin": fundamentals.get("ttm", {}).get("fcf_margin"),
            "net_debt": fundamentals.get("net_debt"),
            "fundamentals_filed_at": fundamentals.get("data_filed_at"),
            "currency": fundamentals.get("currency"),
            "eps_consensus": expectations.get("eps", {}).get("mean"),
            "revision_score": revisions.get("revision_score"),
            "trailing_pe": valuation.get("trailing_pe"),
            "forward_pe": valuation.get("forward_pe"),
            "ev_to_revenue_trailing": valuation.get("ev_to_revenue_trailing"),
            "fcf_yield_trailing": valuation.get("fcf_yield_trailing"),
            "implied_revenue_cagr": implied.get("implied_revenue_cagr"),
            "financial_basis": valuation.get("financial_basis"),
        })
    warnings = []
    if len(price_dates - {None}) > 1:
        warnings.append("price dates differ across tickers")
    if len(filing_dates - {None}) > 1:
        warnings.append("fundamental filing dates differ across tickers")
    if len(currencies - {None}) > 1:
        warnings.append("currencies differ across tickers; raw values are not directly comparable")
    unusable = [
        evidence["ticker"] for evidence in evidence_items
        if not evidence["quality"]["can_research"]
    ]
    if unusable:
        warnings.append(f"insufficient evidence for: {', '.join(unusable)}")
    return {
        "can_research": bool(len(evidence_items) - len(unusable)),
        "can_decide": all(evidence["quality"]["can_decide"] for evidence in evidence_items),
        "tickers": [row["ticker"] for row in rows],
        "rows": rows,
        "warnings": warnings,
    }


def prepare_update(con, ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    ticker = ticker.upper()
    evidence = build_evidence(con, ticker, max_price_age_days)
    previous = repository.get_latest_investment_analysis(con, ticker)
    changes = None
    if previous:
        try:
            price_rows = repository.get_latest_prices(con, ticker, limit=500)
            all_estimates = repository.get_estimate_snapshots(con, ticker, limit=200)
            period = resolve_estimate_period(all_estimates) if all_estimates else None
            estimate_rows = repository.get_estimate_snapshots(
                con, ticker, limit=200, fiscal_period=period,
            ) if period else []
            changes = {
                "status": "OK",
                "fiscal_period": period,
                **compute_change_since(
                    price_rows,
                    estimate_rows,
                    since_date=date.fromisoformat(previous["created_at"][:10]),
                ),
            }
        except ValueError as exc:
            changes = {"status": "MISSING", "message": str(exc)}
    return {
        "ticker": ticker,
        "previous_analysis": previous,
        "changes_since_previous": changes,
        "evidence": evidence,
    }
