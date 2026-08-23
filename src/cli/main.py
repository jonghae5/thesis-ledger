import json
import uuid
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from src.models.enums import Decision, ProviderStatus
from src.models.schemas import (
    CatalystRow, CompanyRow, EstimateSnapshotRow, FundamentalSnapshotRow, GuidanceSnapshotRow,
    InvestmentAnalysisRow, MacroSnapshotRow, PriceRow, Provenance,
)
from src.providers.alpha_vantage import AlphaVantageEstimateProvider, parse_earnings_estimates, parse_earnings_surprises
from src.providers.finnhub import FinnhubEarningsProvider, FinnhubNewsProvider
from src.providers.macro import FearGreedProvider, FredMacroProvider
from src.providers.provider_licensing import commercial_provider_error
from src.providers.sec import SecFilingProvider, extract_fundamental_snapshots
from src.providers.yahoo import YahooEstimateProvider, YahooPriceProvider
from src.services.research import (
    DEFAULT_MAX_PRICE_AGE_DAYS,
    build_evidence,
    compare_evidence,
    fundamentals_payload,
    expectations_payload,
    latest_fundamentals_row as _latest_fundamentals_row,
    market_payload,
    macro_payload,
    prepare_update,
    resolve_estimate_period as _resolve_estimate_period,
    reverse_dcf_payload,
    valuation_fundamentals_row,
    valuation_payload,
    latest_price_record,
)
from src.storage import repository
from src.storage.db import DEFAULT_DB_PATH, get_connection, migrate
from src.tools.catalysts import merge_catalysts
from src.tools.change import compute_change_since
from src.tools.dcf import faded_scenario_metrics, faded_target_price, probability_weighted_value
from src.tools.expectations import compute_earnings_surprise_summary, select_fiscal_year_estimate
from src.tools.revisions import compute_revision_metrics

load_dotenv()

app = typer.Typer()
data_app = typer.Typer(help="Fetch and inspect market/company data.")
valuation_app = typer.Typer(help="Run deterministic valuation calculations.")
analysis_app = typer.Typer(help="Persist and inspect investment-analysis memory.")
app.add_typer(data_app, name="data")
app.add_typer(valuation_app, name="valuation")
app.add_typer(analysis_app, name="analysis")

DB_PATH: Path = DEFAULT_DB_PATH

WATCHLIST = [
    ("NVDA", "NVIDIA Corporation"),
    ("AAPL", "Apple Inc."),
    ("AMD", "Advanced Micro Devices, Inc."),
    ("META", "Meta Platforms, Inc."),
    ("GOOGL", "Alphabet Inc."),
]

def _connect():
    con = get_connection(DB_PATH)
    migrate(con)
    return con


def _fail(payload: dict) -> None:
    typer.echo(json.dumps(payload))
    raise typer.Exit(code=1)


def _provider_attempt(provider: str, result) -> dict:
    return {
        "provider": provider,
        "status": result.status.value,
        "message": result.message,
    }


def _add_years(value: date_cls, years: int) -> date_cls:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _current_fiscal_period(con, ticker: str) -> date_cls:
    today = date_cls.today()
    snapshots = repository.get_estimate_snapshots(con, ticker, limit=200)
    future_periods = sorted({
        date_cls.fromisoformat(row["fiscal_period"])
        for row in snapshots
        if date_cls.fromisoformat(row["fiscal_period"]) >= today
    })
    if future_periods:
        return future_periods[0]

    latest = _latest_fundamentals_row(con, ticker)
    period = date_cls.fromisoformat(latest["period"])
    while period < today:
        period = _add_years(period, 1)
    return period


def _materialize_yahoo_periods(con, ticker: str, rows: list[dict]) -> list[dict]:
    current_period = _current_fiscal_period(con, ticker)
    offsets = {"0y": 0, "+1y": 1}
    return [
        {**row, "date": _add_years(current_period, offsets[row["period"]]).isoformat()}
        for row in rows if row.get("period") in offsets
    ]


def _price_row_from_dict(r: dict) -> PriceRow:
    return PriceRow(
        ticker=r["ticker"], date=r["date"], open=r["open"], high=r["high"],
        low=r["low"], close=r["close"], volume=r["volume"],
        provenance=Provenance(
            source=r["source"], source_url=r["source_url"],
            retrieved_at=r["retrieved_at"], as_of_date=r["as_of_date"],
        ),
    )


def _fundamental_snapshot_row_from_dict(r: dict) -> FundamentalSnapshotRow:
    return FundamentalSnapshotRow(
        ticker=r["ticker"], period=r["period"], filed_at=r["filed_at"],
        accession=r["accession"], form=r["form"], fiscal_year=r.get("fiscal_year"),
        fiscal_period=r.get("fiscal_period"), revenue=r.get("revenue"),
        gross_profit=r.get("gross_profit"), operating_income=r.get("operating_income"),
        net_income=r.get("net_income"), operating_cashflow=r.get("operating_cashflow"),
        capex=r.get("capex"), fcf=r.get("fcf"), cash=r.get("cash"), debt=r.get("debt"),
        shares=r.get("shares"), currency=r.get("currency"),
        provenance=Provenance(
            source=r["source"], source_url=r["source_url"],
            retrieved_at=r["retrieved_at"], as_of_date=r["as_of_date"],
        ),
    )


def _macro_snapshot_row_from_dict(row: dict) -> MacroSnapshotRow:
    return MacroSnapshotRow(
        indicator=row["indicator"], snapshot_at=row["snapshot_at"],
        observation_date=row["observation_date"], value=row["value"], unit=row["unit"],
        source_type=row["source_type"], transformation=row["transformation"],
        reference_date=row.get("reference_date"), reference_value=row.get("reference_value"),
        percentile_5y=row.get("percentile_5y"),
        source=row["source"], source_url=row.get("source_url"), retrieved_at=row["retrieved_at"],
    )


@data_app.command("seed")
def seed_watchlist():
    con = _connect()
    for ticker, name in WATCHLIST:
        repository.upsert_company(con, CompanyRow(ticker=ticker, name=name))
    typer.echo(json.dumps({"seeded": [t for t, _ in WATCHLIST]}))


@data_app.command("fetch")
def fetch(ticker: str):
    ticker = ticker.upper()
    con = _connect()
    result: dict = {"ticker": ticker}

    price_result = YahooPriceProvider().get_prices(ticker)
    if price_result.status == ProviderStatus.OK:
        rows = [_price_row_from_dict(r) for r in price_result.data["rows"]]
        n = repository.upsert_prices(con, rows)
        result["prices"] = {"status": "OK", "rows_written": n}
    else:
        result["prices"] = {"status": price_result.status.value, "message": price_result.message}

    facts_result = SecFilingProvider().get_company_facts(ticker)
    if facts_result.status == ProviderStatus.OK:
        retrieved_at = datetime.now(timezone.utc).isoformat()
        snapshot_dicts = extract_fundamental_snapshots(facts_result.data, ticker, retrieved_at)
        if snapshot_dicts:
            snapshot_rows = [_fundamental_snapshot_row_from_dict(r) for r in snapshot_dicts]
            snapshot_n = repository.upsert_fundamental_snapshots(con, snapshot_rows)
            result["fundamentals"] = {
                "status": "OK", "rows_written": snapshot_n,
            }
        else:
            result["fundamentals"] = {
                "status": "ERROR",
                "message": "SEC response has no supported 10-K/10-Q US-GAAP filing facts",
            }
    else:
        result["fundamentals"] = {"status": facts_result.status.value, "message": facts_result.message}

    typer.echo(json.dumps(result))
    if result["prices"]["status"] != "OK" or result["fundamentals"]["status"] != "OK":
        raise typer.Exit(code=1)


@data_app.command("market")
def market(ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    ticker = ticker.upper()
    con = _connect()
    try:
        payload = market_payload(con, ticker, max_price_age_days)
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@data_app.command("fundamentals")
def fundamentals(ticker: str, as_of: Optional[str] = None):
    ticker = ticker.upper()
    con = _connect()
    try:
        payload = fundamentals_payload(con, ticker, date_cls.fromisoformat(as_of) if as_of else None)
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@data_app.command("expectations")
def expectations(ticker: str, period: str = "current"):
    ticker = ticker.upper()
    con = _connect()
    attempts = []
    chosen = None
    source = None
    source_url = None

    av_result = AlphaVantageEstimateProvider().get_estimates(ticker)
    attempts.append(_provider_attempt("alpha_vantage", av_result))
    if av_result.status == ProviderStatus.OK:
        try:
            chosen = select_fiscal_year_estimate(
                parse_earnings_estimates(av_result.data), period=period, today=date_cls.today(),
            )
            source = "alpha_vantage"
            source_url = "https://www.alphavantage.co/"
        except ValueError as exc:
            attempts[-1] = {"provider": "alpha_vantage", "status": "ERROR", "message": str(exc)}

    if chosen is None:
        yahoo_result = YahooEstimateProvider().get_estimates(ticker)
        attempts.append(_provider_attempt("yahoo_finance", yahoo_result))
        if yahoo_result.status == ProviderStatus.OK:
            try:
                chosen = select_fiscal_year_estimate(
                    _materialize_yahoo_periods(con, ticker, yahoo_result.data["rows"]),
                    period=period, today=date_cls.today(),
                )
                source = "yahoo_finance"
                source_url = f"https://finance.yahoo.com/quote/{ticker}/analysis/"
            except ValueError as exc:
                attempts[-1] = {"provider": "yahoo_finance", "status": "ERROR", "message": str(exc)}

    if chosen is None:
        try:
            stale = expectations_payload(con, ticker)
        except ValueError:
            _fail({
                "ticker": ticker, "status": "ERROR",
                "message": "all consensus providers failed and no stored snapshot is available",
                "provider_attempts": attempts,
            })
        typer.echo(json.dumps({
            **stale, "status": "STALE", "saved": False,
            "message": "all consensus providers failed; using last stored snapshot",
            "provider_attempts": attempts,
        }))
        return

    now = datetime.now(timezone.utc)
    snapshot = EstimateSnapshotRow(
        ticker=ticker, snapshot_at=now, fiscal_period=chosen["date"],
        eps_mean=chosen["eps_mean"], eps_high=chosen["eps_high"], eps_low=chosen["eps_low"],
        revenue_mean=chosen["revenue_mean"], revenue_high=chosen["revenue_high"], revenue_low=chosen["revenue_low"],
        analyst_count=chosen["eps_analyst_count"],
        eps_mean_7d_ago=chosen.get("eps_mean_7d_ago"),
        eps_mean_30d_ago=chosen.get("eps_mean_30d_ago"),
        eps_mean_90d_ago=chosen.get("eps_mean_90d_ago"),
        revenue_mean_7d_ago=chosen.get("revenue_mean_7d_ago"),
        revenue_mean_30d_ago=chosen.get("revenue_mean_30d_ago"),
        revenue_mean_90d_ago=chosen.get("revenue_mean_90d_ago"),
        provenance=Provenance(
            source=source, source_url=source_url, retrieved_at=now, as_of_date=now.date(),
        ),
    )
    repository.insert_estimate_snapshot(con, snapshot)

    typer.echo(json.dumps({
        "ticker": ticker, "status": "OK", "provider": source,
        "fallback_used": source != "alpha_vantage", "provider_attempts": attempts,
        "period": chosen["date"],
        "eps": {"mean": chosen["eps_mean"], "high": chosen["eps_high"], "low": chosen["eps_low"], "analyst_count": chosen["eps_analyst_count"]},
        "revenue": {"mean": chosen["revenue_mean"], "high": chosen["revenue_high"], "low": chosen["revenue_low"], "analyst_count": chosen["revenue_analyst_count"]},
    }))


@data_app.command("revisions")
def revisions(ticker: str, fiscal_period: Optional[str] = None):
    ticker = ticker.upper()
    con = _connect()
    all_snapshots = repository.get_estimate_snapshots(con, ticker, limit=200)
    if not all_snapshots:
        typer.echo(json.dumps({
            "ticker": ticker, "status": "NO_HISTORY",
            "message": "run 'data expectations' at least twice, on different days, before revisions has data",
        }))
        return

    try:
        resolved_period = _resolve_estimate_period(all_snapshots, fiscal_period)
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    snapshots = repository.get_estimate_snapshots(
        con, ticker, limit=200, fiscal_period=resolved_period,
    )

    metrics = compute_revision_metrics(snapshots, now=datetime.now(timezone.utc))
    typer.echo(json.dumps({"ticker": ticker, "fiscal_period": resolved_period, **metrics}))


@data_app.command("earnings-surprise")
def earnings_surprise(ticker: str):
    ticker = ticker.upper()
    attempts = []
    quarterly = None
    provider = None

    av_result = AlphaVantageEstimateProvider().get_earnings_history(ticker)
    attempts.append(_provider_attempt("alpha_vantage", av_result))
    if av_result.status == ProviderStatus.OK:
        quarterly = parse_earnings_surprises(av_result.data)
        if quarterly:
            provider = "alpha_vantage"
        else:
            attempts[-1] = {"provider": "alpha_vantage", "status": "ERROR", "message": "no earnings rows"}

    if not quarterly:
        finnhub_result = FinnhubEarningsProvider().get_earnings_history(ticker)
        attempts.append(_provider_attempt("finnhub", finnhub_result))
        if finnhub_result.status == ProviderStatus.OK:
            quarterly = finnhub_result.data["rows"]
            provider = "finnhub"

    if not quarterly:
        yahoo_result = YahooEstimateProvider().get_earnings_history(ticker)
        attempts.append(_provider_attempt("yahoo_finance", yahoo_result))
        if yahoo_result.status == ProviderStatus.OK:
            quarterly = yahoo_result.data["rows"]
            provider = "yahoo_finance"

    if not quarterly:
        _fail({
            "ticker": ticker, "status": "ERROR",
            "message": "all earnings-surprise providers failed",
            "provider_attempts": attempts,
        })
    try:
        summary = compute_earnings_surprise_summary(quarterly)
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    typer.echo(json.dumps({
        "ticker": ticker, "status": "OK", "provider": provider,
        "fallback_used": provider != "alpha_vantage", "provider_attempts": attempts,
        **summary,
    }))


@data_app.command("evidence")
def evidence(ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    """Build one source-backed package for an investment update."""
    payload = build_evidence(_connect(), ticker, max_price_age_days)
    typer.echo(json.dumps(payload))
    if not payload["quality"]["can_research"]:
        raise typer.Exit(code=1)


@data_app.command("macro-fetch")
def macro_fetch():
    """Append current FRED macro and CNN Fear & Greed snapshots."""
    con = _connect()
    providers = {
        "fred": FredMacroProvider().get_snapshot(),
        "fear_greed": FearGreedProvider().get_snapshot(),
    }
    saved = 0
    statuses = {}
    for name, result in providers.items():
        statuses[name] = {"status": result.status.value, "message": result.message}
        if result.status == ProviderStatus.OK:
            rows = [_macro_snapshot_row_from_dict(row) for row in result.data["rows"]]
            count = repository.insert_macro_snapshots(con, rows)
            statuses[name]["saved"] = count
            saved += count
    payload = {
        "status": "OK" if all(r.status == ProviderStatus.OK for r in providers.values()) else ("PARTIAL" if saved else "ERROR"),
        "saved": saved,
        "providers": statuses,
    }
    typer.echo(json.dumps(payload))
    if not saved:
        raise typer.Exit(code=1)


@data_app.command("macro")
def macro(as_of: Optional[str] = None):
    """Read latest stored macro context without fetching external data."""
    try:
        effective_date = date_cls.fromisoformat(as_of) if as_of else None
    except ValueError:
        _fail({"status": "ERROR", "message": "as_of must be YYYY-MM-DD"})
    payload = macro_payload(_connect(), as_of=effective_date)
    typer.echo(json.dumps(payload))
    if payload["status"] == "MISSING":
        raise typer.Exit(code=1)


@data_app.command("compare")
def compare(tickers: list[str], max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    """Compare two or more companies without inventing a composite score."""
    normalized = list(dict.fromkeys(ticker.upper() for ticker in tickers))
    if len(normalized) < 2:
        _fail({"status": "ERROR", "message": "compare requires at least two unique tickers"})
    con = _connect()
    payload = compare_evidence([
        build_evidence(con, ticker, max_price_age_days) for ticker in normalized
    ])
    typer.echo(json.dumps(payload))
    if not payload["can_research"]:
        raise typer.Exit(code=1)


@analysis_app.command("save-guidance")
def save_guidance(
    ticker: str,
    revenue_low: Optional[float] = None,
    revenue_high: Optional[float] = None,
    margin_guidance: Optional[float] = None,
    capex_guidance: Optional[float] = None,
    fiscal_period: str = typer.Option(...),
    guidance_scope: str = typer.Option(...),
    currency: str = typer.Option(...),
    value_unit: str = typer.Option(...),
    source_filing: str = typer.Option(...),
    source_date: str = typer.Option(...),
):
    ticker = ticker.upper()
    fiscal_period = fiscal_period.upper()
    guidance_scope = guidance_scope.upper()
    currency = currency.upper()
    value_unit = value_unit.upper()
    con = _connect()
    previous_any = repository.get_latest_guidance_snapshot(con, ticker)
    previous = repository.get_latest_guidance_snapshot(
        con, ticker, fiscal_period, guidance_scope, currency, value_unit,
    )

    now = datetime.now(timezone.utc)
    repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
        ticker=ticker, snapshot_at=now, revenue_low=revenue_low, revenue_high=revenue_high,
        margin_guidance=margin_guidance, capex_guidance=capex_guidance,
        fiscal_period=fiscal_period, guidance_scope=guidance_scope,
        currency=currency, value_unit=value_unit,
        source_filing=source_filing, source_date=date_cls.fromisoformat(source_date), retrieved_at=now,
    ))

    if previous is None:
        trend = "FIRST_SNAPSHOT" if previous_any is None else "NOT_COMPARABLE"
    else:
        def _midpoint(low, high):
            if low is not None and high is not None:
                return (low + high) / 2
            return None

        current_mid = _midpoint(revenue_low, revenue_high)
        previous_mid = _midpoint(previous.get("revenue_low"), previous.get("revenue_high"))
        if current_mid is None or previous_mid is None:
            current_mid = margin_guidance
            previous_mid = previous.get("margin_guidance")

        if current_mid is None or previous_mid in (None, 0):
            trend = "UNKNOWN"
        else:
            change = (current_mid - previous_mid) / previous_mid
            trend = "RAISED" if change > 0.005 else ("LOWERED" if change < -0.005 else "MAINTAINED")

    typer.echo(json.dumps({
        "ticker": ticker,
        "trend": trend,
        "comparison_key": {
            "fiscal_period": fiscal_period,
            "guidance_scope": guidance_scope,
            "currency": currency,
            "value_unit": value_unit,
        },
        "previous": previous,
        "latest_other_basis": previous_any if previous is None else None,
    }))


@valuation_app.command("multiples")
def valuation(ticker: str):
    ticker = ticker.upper()
    con = _connect()
    try:
        payload = valuation_payload(con, ticker)
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@valuation_app.command("reverse-dcf")
def reverse_dcf(
    ticker: str,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
):
    ticker = ticker.upper()
    con = _connect()
    try:
        payload = reverse_dcf_payload(
            con, ticker, discount_rate=discount_rate,
            terminal_growth=terminal_growth, years=years,
        )
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@valuation_app.command("scenario")
def scenario(
    ticker: str,
    bear_growth: float = typer.Option(...), bear_margin: float = typer.Option(...), bear_prob: float = typer.Option(...),
    base_growth: float = typer.Option(...), base_margin: float = typer.Option(...), base_prob: float = typer.Option(...),
    bull_growth: float = typer.Option(...), bull_margin: float = typer.Option(...), bull_prob: float = typer.Option(...),
    discount_rate: float = 0.09, terminal_growth: float = 0.025, years: int = 10,
    annual_dilution: float = typer.Option(..., min=0.0, max=0.999999),
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
):
    ticker = ticker.upper()
    con = _connect()
    try:
        fundamentals_row = valuation_fundamentals_row(con, ticker)
        price_row = latest_price_record(con, ticker, max_price_age_days)
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    shares = fundamentals_row.get("shares")
    revenue = fundamentals_row.get("revenue")
    fcf = fundamentals_row.get("fcf")
    debt = fundamentals_row.get("debt")
    cash = fundamentals_row.get("cash")
    if not shares or not revenue or fcf is None or debt is None or cash is None:
        _fail({"ticker": ticker, "status": "ERROR", "message": "fundamentals row missing shares/revenue/fcf/debt/cash"})
    net_debt = debt - cash
    starting_margin = fcf / revenue
    current_price = price_row["close"]

    cases = {
        "bear": (bear_growth, bear_margin, bear_prob),
        "base": (base_growth, base_margin, base_prob),
        "bull": (bull_growth, bull_margin, bull_prob),
    }
    result = {
        "ticker": ticker,
        "financial_basis": fundamentals_row.get("financial_basis"),
        "model": "FADED_DCF",
        "price": current_price,
        "price_as_of": price_row["date"],
        "starting_fcf_margin": starting_margin,
        "terminal_growth": terminal_growth,
        "discount_rate": discount_rate,
        "years": years,
        "annual_dilution": annual_dilution,
    }
    scenario_list = []
    try:
        for name, (growth, margin, prob) in cases.items():
            metrics = faded_scenario_metrics(
                revenue, starting_margin, growth, margin, shares, net_debt,
                current_price, discount_rate, terminal_growth, years, annual_dilution,
            )
            entry = {
                "probability": prob,
                "initial_revenue_growth": growth,
                "mature_fcf_margin": margin,
                **metrics,
            }
            result[name] = entry
            scenario_list.append(entry)
        result["probability_weighted_value"] = probability_weighted_value(scenario_list)
        result["probability_weighted_upside_downside"] = (
            result["probability_weighted_value"] / current_price - 1
        )
        warnings = []
        base_terminal_value_pct = result["base"]["terminal_value_pct"]
        if base_terminal_value_pct is not None and base_terminal_value_pct > 0.75:
            warnings.append("base case terminal value exceeds 75% of enterprise value")
        if result["base"]["cumulative_dilution"] > 0.10:
            warnings.append("base case cumulative dilution exceeds 10%")
        result["warnings"] = warnings
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    typer.echo(json.dumps(result))


@valuation_app.command("sensitivity")
def sensitivity(
    ticker: str,
    growth: float = typer.Option(..., help="Initial revenue growth assumption."),
    mature_margin: float = typer.Option(..., help="FCF margin reached by the final explicit year."),
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
    annual_dilution: float = 0.0,
    growth_step: float = 0.03,
    discount_step: float = 0.01,
):
    """Return a compact 3x3 faded-growth DCF sensitivity table."""
    ticker = ticker.upper()
    try:
        fundamentals_row = valuation_fundamentals_row(_connect(), ticker)
        revenue = fundamentals_row.get("revenue")
        fcf = fundamentals_row.get("fcf")
        shares = fundamentals_row.get("shares")
        debt = fundamentals_row.get("debt")
        cash = fundamentals_row.get("cash")
        if not revenue or fcf is None or not shares or debt is None or cash is None:
            raise ValueError("fundamentals row missing revenue/fcf/shares/debt/cash")
        starting_margin = fcf / revenue
        growth_values = [growth - growth_step, growth, growth + growth_step]
        discount_values = [discount_rate - discount_step, discount_rate, discount_rate + discount_step]
        matrix = []
        for growth_value in growth_values:
            values = {}
            for rate in discount_values:
                values[f"{rate:.4f}"] = faded_target_price(
                    revenue, starting_margin, growth_value, mature_margin,
                    shares, debt - cash, rate, terminal_growth, years,
                    annual_dilution,
                )
            matrix.append({"initial_growth": growth_value, "values_by_discount_rate": values})
    except ValueError as exc:
        _fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    typer.echo(json.dumps({
        "ticker": ticker,
        "financial_basis": fundamentals_row.get("financial_basis"),
        "starting_fcf_margin": starting_margin,
        "mature_fcf_margin": mature_margin,
        "terminal_growth": terminal_growth,
        "years": years,
        "annual_dilution": annual_dilution,
        "discount_rates": discount_values,
        "matrix": matrix,
        "source_type": "MODEL_OUTPUT",
    }))


@data_app.command("catalysts")
def catalysts(ticker: str):
    ticker = ticker.upper()
    con = _connect()
    stored = repository.get_catalysts(con, ticker)
    attempts = []

    calendar_result = AlphaVantageEstimateProvider().get_earnings_calendar(ticker)
    attempts.append(_provider_attempt("alpha_vantage", calendar_result))
    calendar_rows = calendar_result.data["rows"] if calendar_result.status == ProviderStatus.OK else []
    calendar_source = "alpha_vantage" if calendar_rows else None

    if not calendar_rows:
        finnhub_result = FinnhubEarningsProvider().get_earnings_calendar(ticker)
        attempts.append(_provider_attempt("finnhub", finnhub_result))
        if finnhub_result.status == ProviderStatus.OK:
            calendar_rows = finnhub_result.data["rows"]
            calendar_source = "finnhub"

    if not calendar_rows:
        yahoo_result = YahooEstimateProvider().get_earnings_calendar(ticker)
        attempts.append(_provider_attempt("yahoo_finance", yahoo_result))
        if yahoo_result.status == ProviderStatus.OK:
            calendar_rows = yahoo_result.data["rows"]
            calendar_source = "yahoo_finance"

    merged = merge_catalysts(stored, calendar_rows)

    typer.echo(json.dumps({
        "ticker": ticker,
        "catalysts": merged,
        "calendar_status": "OK" if calendar_rows else "DEGRADED",
        "calendar_source": calendar_source,
        "calendar_message": None if calendar_rows else "all calendar providers failed; using stored catalysts only",
        "provider_attempts": attempts,
    }))


@data_app.command("news")
def news(ticker: str, days: int = 7, limit: int = typer.Option(20, min=1, max=100)):
    ticker = ticker.upper()
    result = FinnhubNewsProvider().get_news(ticker, days=days)
    if result.status != ProviderStatus.OK:
        _fail({"ticker": ticker, "status": result.status.value, "message": result.message})
    rows = result.data["rows"][:limit]
    typer.echo(json.dumps({
        "ticker": ticker, "days": days, "limit": limit,
        "returned": len(rows), "news": rows,
    }))


@analysis_app.command("save-catalyst")
def save_catalyst(
    ticker: str,
    event_date: str = typer.Option(...),
    event_type: str = typer.Option(...),
    description: str = typer.Option(...),
    importance: str = typer.Option(...),
):
    ticker = ticker.upper()
    con = _connect()
    repository.insert_catalyst(con, CatalystRow(
        ticker=ticker, event_date=date_cls.fromisoformat(event_date),
        event_type=event_type, description=description, importance=importance,
    ))
    typer.echo(json.dumps({"ticker": ticker, "saved": True}))


@analysis_app.command("save")
def save_analysis(
    ticker: str,
    decision: str = typer.Option(...),
    confidence: float = typer.Option(...),
    expected_return: float = typer.Option(...),
    expected_return_horizon_months: int = typer.Option(..., min=1),
    expected_return_method: str = typer.Option(...),
    expected_return_basis: str = typer.Option(...),
    price: float = typer.Option(...),
    thesis_json: str = typer.Option(...),
    variant_perception_json: str = typer.Option(...),
    invalidation_json: str = typer.Option(...),
    bull_value: Optional[float] = None,
    base_value: Optional[float] = None,
    bear_value: Optional[float] = None,
    run_id: Optional[str] = None,
    model_name: Optional[str] = None,
    model_version: Optional[str] = None,
    prompt_version: Optional[str] = None,
    input_snapshot_json: Optional[str] = None,
    assumptions_json: Optional[str] = None,
):
    ticker = ticker.upper()

    valid_return_methods = {
        "PROBABILITY_WEIGHTED_SCENARIO", "BASE_CASE_TARGET", "DCF_IRR", "OTHER",
    }
    expected_return_method = expected_return_method.upper()
    if expected_return_method not in valid_return_methods:
        _fail({
            "ticker": ticker, "status": "ERROR",
            "message": f"invalid expected return method '{expected_return_method}', expected one of: {', '.join(sorted(valid_return_methods))}",
        })
    valid_return_bases = {"PRICE_RETURN", "TOTAL_RETURN"}
    expected_return_basis = expected_return_basis.upper()
    if expected_return_basis not in valid_return_bases:
        _fail({
            "ticker": ticker, "status": "ERROR",
            "message": f"invalid expected return basis '{expected_return_basis}', expected one of: {', '.join(sorted(valid_return_bases))}",
        })
    if expected_return <= -1:
        _fail({
            "ticker": ticker, "status": "ERROR",
            "message": "expected_return must be greater than -1.0",
        })
    expected_return_annualized = (1 + expected_return) ** (12 / expected_return_horizon_months) - 1

    try:
        decision_enum = Decision(decision)
    except ValueError:
        valid = ", ".join(d.value for d in Decision)
        _fail({"ticker": ticker, "status": "ERROR", "message": f"invalid decision '{decision}', expected one of: {valid}"})

    json_fields = [
        ("thesis_json", thesis_json, list),
        ("variant_perception_json", variant_perception_json, dict),
        ("invalidation_json", invalidation_json, list),
        ("input_snapshot_json", input_snapshot_json or "{}", dict),
        ("assumptions_json", assumptions_json or "[]", list),
    ]
    for field_name, raw, expected_type in json_fields:
        try:
            parsed_json = json.loads(raw)
        except json.JSONDecodeError as exc:
            _fail({"ticker": ticker, "status": "ERROR", "message": f"{field_name} is not valid JSON: {exc}"})
        if not isinstance(parsed_json, expected_type):
            _fail({
                "ticker": ticker, "status": "ERROR",
                "message": f"{field_name} must contain a JSON {expected_type.__name__}",
            })

    resolved_run_id = run_id or str(uuid.uuid4())
    audit_complete = all([model_name, model_version, prompt_version, input_snapshot_json])

    con = _connect()
    evidence = build_evidence(con, ticker)
    if not evidence["quality"]["can_decide"]:
        _fail({
            "ticker": ticker,
            "status": "RESEARCH_ONLY",
            "message": "directional analysis requires a usable expectation anchor",
            "quality": evidence["quality"],
        })
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker=ticker, created_at=datetime.now(timezone.utc), price=price,
        decision=decision_enum, confidence=confidence, expected_return=expected_return,
        expected_return_horizon_months=expected_return_horizon_months,
        expected_return_method=expected_return_method,
        expected_return_annualized=expected_return_annualized,
        expected_return_basis=expected_return_basis,
        bull_value=bull_value, base_value=base_value, bear_value=bear_value,
        thesis_json=thesis_json, variant_perception_json=variant_perception_json, invalidation_json=invalidation_json,
        run_id=resolved_run_id, model_name=model_name, model_version=model_version,
        prompt_version=prompt_version, input_snapshot_json=input_snapshot_json or "{}",
        assumptions_json=assumptions_json or "[]",
    ))
    typer.echo(json.dumps({
        "ticker": ticker, "saved": True, "run_id": resolved_run_id,
        "audit_complete": audit_complete,
        "expected_return_annualized": expected_return_annualized,
    }))


@analysis_app.command("latest")
def get_latest_analysis(ticker: str):
    ticker = ticker.upper()
    con = _connect()
    latest = repository.get_latest_investment_analysis(con, ticker)
    if latest is None:
        typer.echo(json.dumps({"ticker": ticker, "status": "NO_HISTORY", "message": "no previous investment_analysis row for this ticker"}))
        return
    typer.echo(json.dumps(latest))


@analysis_app.command("history")
def analysis_history(ticker: str, limit: int = 20):
    ticker = ticker.upper()
    con = _connect()
    history = repository.get_investment_analysis_history(con, ticker, limit=limit)
    typer.echo(json.dumps({"ticker": ticker, "history": history}))


@analysis_app.command("change-since")
def change_since(
    ticker: str,
    since_date: str = typer.Option(...),
    fiscal_period: Optional[str] = None,
):
    ticker = ticker.upper()
    con = _connect()
    price_rows = repository.get_latest_prices(con, ticker, limit=500)
    if not price_rows:
        _fail({"ticker": ticker, "status": "ERROR", "message": f"no stored price for {ticker} - run 'data fetch' first"})

    all_estimates = repository.get_estimate_snapshots(con, ticker, limit=200)
    resolved_period = _resolve_estimate_period(all_estimates, fiscal_period) if all_estimates else None
    estimate_rows = repository.get_estimate_snapshots(
        con, ticker, limit=200, fiscal_period=resolved_period,
    ) if resolved_period else []
    result = compute_change_since(price_rows, estimate_rows, since_date=date_cls.fromisoformat(since_date))
    typer.echo(json.dumps({"ticker": ticker, "fiscal_period": resolved_period, **result}))


@analysis_app.command("prepare")
def prepare(ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    """Prepare prior thesis, changes, and current evidence for Codex synthesis."""
    payload = prepare_update(_connect(), ticker, max_price_age_days)
    typer.echo(json.dumps(payload))
    if not payload["evidence"]["quality"]["can_research"]:
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor():
    """Run production-safety checks without changing investment data."""
    con = _connect()
    failures: list[str] = []
    warnings: list[str] = []

    for provider in ("yahoo_finance", "alpha_vantage", "finnhub"):
        error = commercial_provider_error(provider)
        if error:
            failures.append(error)

    snapshot_count = con.execute("SELECT COUNT(*) FROM fundamental_snapshots").fetchone()[0]
    if snapshot_count == 0:
        warnings.append("no point-in-time fundamental snapshots; run fetch")

    unaudited_count = con.execute(
        """
        SELECT COUNT(*) FROM investment_analysis
        WHERE model_name IS NULL OR model_version IS NULL
           OR prompt_version IS NULL OR input_snapshot_json IS NULL
        """
    ).fetchone()[0]
    if unaudited_count:
        warnings.append(f"{unaudited_count} investment analyses lack complete reproducibility metadata")

    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    typer.echo(json.dumps({
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "fundamental_snapshot_count": snapshot_count,
        "unaudited_analysis_count": unaudited_count,
    }))
    if failures:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
