import json

import typer

from src.cli.common import connect, fail, provider_attempt
from src.models.enums import ProviderStatus
from src.providers.alpha_vantage import AlphaVantageEstimateProvider
from src.providers.finnhub import FinnhubEarningsProvider, FinnhubNewsProvider
from src.providers.yahoo import YahooEstimateProvider
from src.storage import repository
from src.tools.catalysts import merge_catalysts


def catalysts(ticker: str):
    ticker = ticker.upper()
    stored = repository.get_catalysts(connect(), ticker)
    attempts = []

    calendar_result = AlphaVantageEstimateProvider().get_earnings_calendar(ticker)
    attempts.append(provider_attempt("alpha_vantage", calendar_result))
    calendar_rows = calendar_result.data["rows"] if calendar_result.status == ProviderStatus.OK else []
    calendar_source = "alpha_vantage" if calendar_rows else None

    if not calendar_rows:
        finnhub_result = FinnhubEarningsProvider().get_earnings_calendar(ticker)
        attempts.append(provider_attempt("finnhub", finnhub_result))
        if finnhub_result.status == ProviderStatus.OK:
            calendar_rows = finnhub_result.data["rows"]
            calendar_source = "finnhub"

    if not calendar_rows:
        yahoo_result = YahooEstimateProvider().get_earnings_calendar(ticker)
        attempts.append(provider_attempt("yahoo_finance", yahoo_result))
        if yahoo_result.status == ProviderStatus.OK:
            calendar_rows = yahoo_result.data["rows"]
            calendar_source = "yahoo_finance"

    typer.echo(json.dumps({
        "ticker": ticker,
        "catalysts": merge_catalysts(stored, calendar_rows),
        "calendar_status": "OK" if calendar_rows else "DEGRADED",
        "calendar_source": calendar_source,
        "calendar_message": (
            None if calendar_rows else "all calendar providers failed; using stored catalysts only"
        ),
        "provider_attempts": attempts,
    }))


def news(
    ticker: str,
    days: int = 7,
    limit: int = typer.Option(20, min=1, max=100),
):
    ticker = ticker.upper()
    result = FinnhubNewsProvider().get_news(ticker, days=days)
    if result.status != ProviderStatus.OK:
        fail({"ticker": ticker, "status": result.status.value, "message": result.message})
    rows = result.data["rows"][:limit]
    typer.echo(json.dumps({
        "ticker": ticker,
        "days": days,
        "limit": limit,
        "returned": len(rows),
        "news": rows,
    }))
