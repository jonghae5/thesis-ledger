import json
from datetime import date, datetime, timezone

import typer

from src.cli.common import connect, fail, provider_attempt
from src.models.enums import ProviderStatus
from src.models.schemas import EstimateSnapshotRow, Provenance
from src.providers.alpha_vantage import (
    AlphaVantageEstimateProvider,
    parse_earnings_estimates,
    parse_earnings_surprises,
)
from src.providers.finnhub import FinnhubEarningsProvider
from src.providers.yahoo import YahooEstimateProvider
from src.services.research import expectations_payload, latest_fundamentals_row, resolve_estimate_period
from src.storage import repository
from src.tools.expectations import compute_earnings_surprise_summary, select_fiscal_year_estimate
from src.tools.revisions import compute_revision_metrics


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _current_fiscal_period(con, ticker: str) -> date:
    today = date.today()
    snapshots = repository.get_estimate_snapshots(con, ticker, limit=200)
    future_periods = sorted({
        date.fromisoformat(row["fiscal_period"])
        for row in snapshots
        if date.fromisoformat(row["fiscal_period"]) >= today
    })
    if future_periods:
        return future_periods[0]

    latest = latest_fundamentals_row(con, ticker)
    period = date.fromisoformat(latest["period"])
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


def expectations(ticker: str, period: str = "current"):
    ticker = ticker.upper()
    con = connect()
    attempts = []
    chosen = None
    source = None
    source_url = None

    av_result = AlphaVantageEstimateProvider().get_estimates(ticker)
    attempts.append(provider_attempt("alpha_vantage", av_result))
    if av_result.status == ProviderStatus.OK:
        try:
            chosen = select_fiscal_year_estimate(
                parse_earnings_estimates(av_result.data), period=period, today=date.today(),
            )
            source = "alpha_vantage"
            source_url = "https://www.alphavantage.co/"
        except ValueError as exc:
            attempts[-1] = {"provider": "alpha_vantage", "status": "ERROR", "message": str(exc)}

    if chosen is None:
        yahoo_result = YahooEstimateProvider().get_estimates(ticker)
        attempts.append(provider_attempt("yahoo_finance", yahoo_result))
        if yahoo_result.status == ProviderStatus.OK:
            try:
                chosen = select_fiscal_year_estimate(
                    _materialize_yahoo_periods(con, ticker, yahoo_result.data["rows"]),
                    period=period,
                    today=date.today(),
                )
                source = "yahoo_finance"
                source_url = f"https://finance.yahoo.com/quote/{ticker}/analysis/"
            except ValueError as exc:
                attempts[-1] = {"provider": "yahoo_finance", "status": "ERROR", "message": str(exc)}

    if chosen is None:
        try:
            stale = expectations_payload(con, ticker)
        except ValueError:
            fail({
                "ticker": ticker,
                "status": "ERROR",
                "message": "all consensus providers failed and no stored snapshot is available",
                "provider_attempts": attempts,
            })
        typer.echo(json.dumps({
            **stale,
            "status": "STALE",
            "saved": False,
            "message": "all consensus providers failed; using last stored snapshot",
            "provider_attempts": attempts,
        }))
        return

    now = datetime.now(timezone.utc)
    snapshot = EstimateSnapshotRow(
        ticker=ticker, snapshot_at=now, fiscal_period=chosen["date"],
        eps_mean=chosen["eps_mean"], eps_high=chosen["eps_high"], eps_low=chosen["eps_low"],
        revenue_mean=chosen["revenue_mean"], revenue_high=chosen["revenue_high"],
        revenue_low=chosen["revenue_low"], analyst_count=chosen["eps_analyst_count"],
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
        "ticker": ticker,
        "status": "OK",
        "provider": source,
        "fallback_used": source != "alpha_vantage",
        "provider_attempts": attempts,
        "period": chosen["date"],
        "eps": {
            "mean": chosen["eps_mean"], "high": chosen["eps_high"],
            "low": chosen["eps_low"], "analyst_count": chosen["eps_analyst_count"],
        },
        "revenue": {
            "mean": chosen["revenue_mean"], "high": chosen["revenue_high"],
            "low": chosen["revenue_low"], "analyst_count": chosen["revenue_analyst_count"],
        },
    }))


def revisions(ticker: str, fiscal_period: str | None = None):
    ticker = ticker.upper()
    con = connect()
    all_snapshots = repository.get_estimate_snapshots(con, ticker, limit=200)
    if not all_snapshots:
        typer.echo(json.dumps({
            "ticker": ticker,
            "status": "NO_HISTORY",
            "message": "run 'data expectations' at least twice, on different days, before revisions has data",
        }))
        return

    try:
        resolved_period = resolve_estimate_period(all_snapshots, fiscal_period)
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    snapshots = repository.get_estimate_snapshots(
        con, ticker, limit=200, fiscal_period=resolved_period,
    )
    metrics = compute_revision_metrics(snapshots, now=datetime.now(timezone.utc))
    typer.echo(json.dumps({"ticker": ticker, "fiscal_period": resolved_period, **metrics}))


def earnings_surprise(ticker: str):
    ticker = ticker.upper()
    attempts = []
    quarterly = None
    provider = None

    av_result = AlphaVantageEstimateProvider().get_earnings_history(ticker)
    attempts.append(provider_attempt("alpha_vantage", av_result))
    if av_result.status == ProviderStatus.OK:
        quarterly = parse_earnings_surprises(av_result.data)
        if quarterly:
            provider = "alpha_vantage"
        else:
            attempts[-1] = {"provider": "alpha_vantage", "status": "ERROR", "message": "no earnings rows"}

    if not quarterly:
        finnhub_result = FinnhubEarningsProvider().get_earnings_history(ticker)
        attempts.append(provider_attempt("finnhub", finnhub_result))
        if finnhub_result.status == ProviderStatus.OK:
            quarterly = finnhub_result.data["rows"]
            provider = "finnhub"

    if not quarterly:
        yahoo_result = YahooEstimateProvider().get_earnings_history(ticker)
        attempts.append(provider_attempt("yahoo_finance", yahoo_result))
        if yahoo_result.status == ProviderStatus.OK:
            quarterly = yahoo_result.data["rows"]
            provider = "yahoo_finance"

    if not quarterly:
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": "all earnings-surprise providers failed",
            "provider_attempts": attempts,
        })
    try:
        summary = compute_earnings_surprise_summary(quarterly)
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    typer.echo(json.dumps({
        "ticker": ticker,
        "status": "OK",
        "provider": provider,
        "fallback_used": provider != "alpha_vantage",
        "provider_attempts": attempts,
        **summary,
    }))
