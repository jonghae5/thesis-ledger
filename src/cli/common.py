import json
from pathlib import Path

import typer

from src.providers.provider_licensing import commercial_provider_error
from src.storage.db import DEFAULT_DB_PATH, get_connection, migrate


DB_PATH: Path = DEFAULT_DB_PATH


def connect():
    con = get_connection(DB_PATH)
    migrate(con)
    return con


def fail(payload: dict) -> None:
    typer.echo(json.dumps(payload))
    raise typer.Exit(code=1)


def provider_attempt(provider: str, result) -> dict:
    return {
        "provider": provider,
        "status": result.status.value,
        "message": result.message,
    }


def production_safety_report() -> dict:
    con = connect()
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

    return {
        "status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        "failures": failures,
        "warnings": warnings,
        "fundamental_snapshot_count": snapshot_count,
        "unaudited_analysis_count": unaudited_count,
    }
