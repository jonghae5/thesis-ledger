import json
from datetime import date as date_cls
from datetime import datetime, timezone

import typer

from src.cli.common import connect, fail
from src.cli.events import catalysts, news
from src.cli.expectations import earnings_surprise, expectations, revisions
from src.cli.macro import macro, macro_fetch
from src.models.enums import ProviderStatus
from src.models.schemas import CompanyRow, FundamentalSnapshotRow, PriceRow, Provenance
from src.providers.sec import SecFilingProvider, extract_fundamental_snapshots
from src.providers.yahoo import YahooPriceProvider
from src.services import evidence as evidence_service
from src.services.research import (
    DEFAULT_MAX_PRICE_AGE_DAYS,
    fundamentals_payload,
    market_payload,
)
from src.storage import repository


data_app = typer.Typer(help="Fetch and inspect market/company data.")

WATCHLIST = [
    ("NVDA", "NVIDIA Corporation"),
    ("AAPL", "Apple Inc."),
    ("AMD", "Advanced Micro Devices, Inc."),
    ("META", "Meta Platforms, Inc."),
    ("GOOGL", "Alphabet Inc."),
]


def _price_row_from_dict(row: dict) -> PriceRow:
    return PriceRow(
        ticker=row["ticker"], date=row["date"], open=row["open"], high=row["high"],
        low=row["low"], close=row["close"], volume=row["volume"],
        provenance=Provenance(
            source=row["source"], source_url=row["source_url"],
            retrieved_at=row["retrieved_at"], as_of_date=row["as_of_date"],
        ),
    )


def _fundamental_snapshot_row_from_dict(row: dict) -> FundamentalSnapshotRow:
    return FundamentalSnapshotRow(
        ticker=row["ticker"], period=row["period"], filed_at=row["filed_at"],
        accession=row["accession"], form=row["form"], fiscal_year=row.get("fiscal_year"),
        fiscal_period=row.get("fiscal_period"), revenue=row.get("revenue"),
        gross_profit=row.get("gross_profit"), operating_income=row.get("operating_income"),
        net_income=row.get("net_income"), operating_cashflow=row.get("operating_cashflow"),
        capex=row.get("capex"), fcf=row.get("fcf"), cash=row.get("cash"), debt=row.get("debt"),
        shares=row.get("shares"), currency=row.get("currency"),
        provenance=Provenance(
            source=row["source"], source_url=row["source_url"],
            retrieved_at=row["retrieved_at"], as_of_date=row["as_of_date"],
        ),
    )


@data_app.command("seed")
def seed_watchlist():
    con = connect()
    for ticker, name in WATCHLIST:
        repository.upsert_company(con, CompanyRow(ticker=ticker, name=name))
    typer.echo(json.dumps({"seeded": [ticker for ticker, _ in WATCHLIST]}))


@data_app.command("fetch")
def fetch(ticker: str):
    ticker = ticker.upper()
    con = connect()
    result: dict = {"ticker": ticker}

    price_result = YahooPriceProvider().get_prices(ticker)
    if price_result.status == ProviderStatus.OK:
        rows = [_price_row_from_dict(row) for row in price_result.data["rows"]]
        result["prices"] = {"status": "OK", "rows_written": repository.upsert_prices(con, rows)}
    else:
        result["prices"] = {"status": price_result.status.value, "message": price_result.message}

    facts_result = SecFilingProvider().get_company_facts(ticker)
    if facts_result.status == ProviderStatus.OK:
        retrieved_at = datetime.now(timezone.utc).isoformat()
        snapshot_dicts = extract_fundamental_snapshots(facts_result.data, ticker, retrieved_at)
        if snapshot_dicts:
            snapshot_rows = [_fundamental_snapshot_row_from_dict(row) for row in snapshot_dicts]
            result["fundamentals"] = {
                "status": "OK",
                "rows_written": repository.upsert_fundamental_snapshots(con, snapshot_rows),
            }
        else:
            result["fundamentals"] = {
                "status": "ERROR",
                "message": "SEC response has no supported 10-K/10-Q US-GAAP filing facts",
            }
    else:
        result["fundamentals"] = {
            "status": facts_result.status.value,
            "message": facts_result.message,
        }

    typer.echo(json.dumps(result))
    if result["prices"]["status"] != "OK" or result["fundamentals"]["status"] != "OK":
        raise typer.Exit(code=1)


@data_app.command("market")
def market(ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    ticker = ticker.upper()
    try:
        payload = market_payload(connect(), ticker, max_price_age_days)
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@data_app.command("fundamentals")
def fundamentals(ticker: str, as_of: str | None = None):
    ticker = ticker.upper()
    try:
        payload = fundamentals_payload(
            connect(), ticker, date_cls.fromisoformat(as_of) if as_of else None,
        )
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@data_app.command("evidence")
def evidence(ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    """Build one source-backed package for an investment update."""
    payload = evidence_service.build_evidence(connect(), ticker, max_price_age_days)
    typer.echo(json.dumps(payload))
    if not payload["quality"]["can_research"]:
        raise typer.Exit(code=1)


@data_app.command("compare")
def compare(tickers: list[str], max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    """Compare two or more companies without inventing a composite score."""
    normalized = list(dict.fromkeys(ticker.upper() for ticker in tickers))
    if len(normalized) < 2:
        fail({"status": "ERROR", "message": "compare requires at least two unique tickers"})
    con = connect()
    payload = evidence_service.compare_evidence([
        evidence_service.build_evidence(con, ticker, max_price_age_days)
        for ticker in normalized
    ])
    typer.echo(json.dumps(payload))
    if not payload["can_research"]:
        raise typer.Exit(code=1)


data_app.command("expectations")(expectations)
data_app.command("revisions")(revisions)
data_app.command("earnings-surprise")(earnings_surprise)
data_app.command("macro-fetch")(macro_fetch)
data_app.command("macro")(macro)
data_app.command("catalysts")(catalysts)
data_app.command("news")(news)
