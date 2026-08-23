import json
from datetime import date

import typer

from src.cli.common import connect, fail
from src.models.enums import ProviderStatus
from src.models.schemas import MacroSnapshotRow
from src.providers.macro import FearGreedProvider, FredMacroProvider
from src.services.research import macro_payload
from src.storage import repository


def _macro_snapshot_row_from_dict(row: dict) -> MacroSnapshotRow:
    return MacroSnapshotRow(
        indicator=row["indicator"], snapshot_at=row["snapshot_at"],
        observation_date=row["observation_date"], value=row["value"], unit=row["unit"],
        source_type=row["source_type"], transformation=row["transformation"],
        reference_date=row.get("reference_date"), reference_value=row.get("reference_value"),
        percentile_5y=row.get("percentile_5y"), source=row["source"],
        source_url=row.get("source_url"), retrieved_at=row["retrieved_at"],
    )


def macro_fetch():
    """Append current FRED macro and CNN Fear & Greed snapshots."""
    con = connect()
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
        "status": (
            "OK" if all(result.status == ProviderStatus.OK for result in providers.values())
            else ("PARTIAL" if saved else "ERROR")
        ),
        "saved": saved,
        "providers": statuses,
    }
    typer.echo(json.dumps(payload))
    if not saved:
        raise typer.Exit(code=1)


def macro(as_of: str | None = None):
    """Read latest stored macro context without fetching external data."""
    try:
        effective_date = date.fromisoformat(as_of) if as_of else None
    except ValueError:
        fail({"status": "ERROR", "message": "as_of must be YYYY-MM-DD"})
    payload = macro_payload(connect(), as_of=effective_date)
    typer.echo(json.dumps(payload))
    if payload["status"] == "MISSING":
        raise typer.Exit(code=1)
