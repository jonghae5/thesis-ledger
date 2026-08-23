import json
import uuid
from datetime import date, datetime, timezone

import typer

from src.cli.common import connect, fail
from src.models.enums import Decision
from src.models.schemas import CatalystRow, GuidanceSnapshotRow, InvestmentAnalysisRow
from src.services import evidence as evidence_service
from src.services.research import DEFAULT_MAX_PRICE_AGE_DAYS, resolve_estimate_period
from src.storage import repository
from src.tools.change import compute_change_since


analysis_app = typer.Typer(help="Persist and inspect investment-analysis memory.")


def _midpoint(low, high):
    if low is not None and high is not None:
        return (low + high) / 2
    return None


def _guidance_trend(previous: dict | None, revenue_low, revenue_high, margin_guidance) -> str:
    if previous is None:
        return "FIRST_SNAPSHOT"
    current_value = _midpoint(revenue_low, revenue_high)
    previous_value = _midpoint(previous.get("revenue_low"), previous.get("revenue_high"))
    if current_value is None or previous_value is None:
        current_value = margin_guidance
        previous_value = previous.get("margin_guidance")
    if current_value is None or previous_value in (None, 0):
        return "UNKNOWN"
    change = (current_value - previous_value) / previous_value
    return "RAISED" if change > 0.005 else ("LOWERED" if change < -0.005 else "MAINTAINED")


@analysis_app.command("save-guidance")
def save_guidance(
    ticker: str,
    revenue_low: float | None = None,
    revenue_high: float | None = None,
    margin_guidance: float | None = None,
    capex_guidance: float | None = None,
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
    con = connect()
    previous_any = repository.get_latest_guidance_snapshot(con, ticker)
    previous = repository.get_latest_guidance_snapshot(
        con, ticker, fiscal_period, guidance_scope, currency, value_unit,
    )

    now = datetime.now(timezone.utc)
    repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
        ticker=ticker, snapshot_at=now, revenue_low=revenue_low, revenue_high=revenue_high,
        margin_guidance=margin_guidance, capex_guidance=capex_guidance,
        fiscal_period=fiscal_period, guidance_scope=guidance_scope,
        currency=currency, value_unit=value_unit, source_filing=source_filing,
        source_date=date.fromisoformat(source_date), retrieved_at=now,
    ))

    trend = _guidance_trend(previous, revenue_low, revenue_high, margin_guidance)
    if previous is None and previous_any is not None:
        trend = "NOT_COMPARABLE"
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


@analysis_app.command("save-catalyst")
def save_catalyst(
    ticker: str,
    event_date: str = typer.Option(...),
    event_type: str = typer.Option(...),
    description: str = typer.Option(...),
    importance: str = typer.Option(...),
):
    ticker = ticker.upper()
    repository.insert_catalyst(connect(), CatalystRow(
        ticker=ticker, event_date=date.fromisoformat(event_date),
        event_type=event_type, description=description, importance=importance,
    ))
    typer.echo(json.dumps({"ticker": ticker, "saved": True}))


def _validate_json_fields(ticker: str, fields: list[tuple[str, str, type]]) -> None:
    for field_name, raw, expected_type in fields:
        try:
            parsed_json = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail({
                "ticker": ticker,
                "status": "ERROR",
                "message": f"{field_name} is not valid JSON: {exc}",
            })
        if not isinstance(parsed_json, expected_type):
            fail({
                "ticker": ticker,
                "status": "ERROR",
                "message": f"{field_name} must contain a JSON {expected_type.__name__}",
            })


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
    bull_value: float | None = None,
    base_value: float | None = None,
    bear_value: float | None = None,
    run_id: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    prompt_version: str | None = None,
    input_snapshot_json: str | None = None,
    assumptions_json: str | None = None,
):
    ticker = ticker.upper()
    valid_return_methods = {
        "PROBABILITY_WEIGHTED_SCENARIO", "BASE_CASE_TARGET", "DCF_IRR", "OTHER",
    }
    expected_return_method = expected_return_method.upper()
    if expected_return_method not in valid_return_methods:
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": (
                f"invalid expected return method '{expected_return_method}', expected one of: "
                f"{', '.join(sorted(valid_return_methods))}"
            ),
        })
    valid_return_bases = {"PRICE_RETURN", "TOTAL_RETURN"}
    expected_return_basis = expected_return_basis.upper()
    if expected_return_basis not in valid_return_bases:
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": (
                f"invalid expected return basis '{expected_return_basis}', expected one of: "
                f"{', '.join(sorted(valid_return_bases))}"
            ),
        })
    if expected_return <= -1:
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": "expected_return must be greater than -1.0",
        })
    expected_return_annualized = (
        (1 + expected_return) ** (12 / expected_return_horizon_months) - 1
    )

    try:
        decision_enum = Decision(decision)
    except ValueError:
        valid = ", ".join(item.value for item in Decision)
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": f"invalid decision '{decision}', expected one of: {valid}",
        })

    _validate_json_fields(ticker, [
        ("thesis_json", thesis_json, list),
        ("variant_perception_json", variant_perception_json, dict),
        ("invalidation_json", invalidation_json, list),
        ("input_snapshot_json", input_snapshot_json or "{}", dict),
        ("assumptions_json", assumptions_json or "[]", list),
    ])

    resolved_run_id = run_id or str(uuid.uuid4())
    audit_complete = all([model_name, model_version, prompt_version, input_snapshot_json])
    con = connect()
    evidence = evidence_service.build_evidence(con, ticker)
    if not evidence["quality"]["can_decide"]:
        fail({
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
        expected_return_basis=expected_return_basis, bull_value=bull_value,
        base_value=base_value, bear_value=bear_value, thesis_json=thesis_json,
        variant_perception_json=variant_perception_json, invalidation_json=invalidation_json,
        run_id=resolved_run_id, model_name=model_name, model_version=model_version,
        prompt_version=prompt_version, input_snapshot_json=input_snapshot_json or "{}",
        assumptions_json=assumptions_json or "[]",
    ))
    typer.echo(json.dumps({
        "ticker": ticker,
        "saved": True,
        "run_id": resolved_run_id,
        "audit_complete": audit_complete,
        "expected_return_annualized": expected_return_annualized,
    }))


@analysis_app.command("latest")
def get_latest_analysis(ticker: str):
    ticker = ticker.upper()
    latest = repository.get_latest_investment_analysis(connect(), ticker)
    if latest is None:
        typer.echo(json.dumps({
            "ticker": ticker,
            "status": "NO_HISTORY",
            "message": "no previous investment_analysis row for this ticker",
        }))
        return
    typer.echo(json.dumps(latest))


@analysis_app.command("history")
def analysis_history(ticker: str, limit: int = 20):
    ticker = ticker.upper()
    history = repository.get_investment_analysis_history(connect(), ticker, limit=limit)
    typer.echo(json.dumps({"ticker": ticker, "history": history}))


@analysis_app.command("change-since")
def change_since(
    ticker: str,
    since_date: str = typer.Option(...),
    fiscal_period: str | None = None,
):
    ticker = ticker.upper()
    con = connect()
    price_rows = repository.get_latest_prices(con, ticker, limit=500)
    if not price_rows:
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": f"no stored price for {ticker} - run 'data fetch' first",
        })
    all_estimates = repository.get_estimate_snapshots(con, ticker, limit=200)
    resolved_period = resolve_estimate_period(all_estimates, fiscal_period) if all_estimates else None
    estimate_rows = repository.get_estimate_snapshots(
        con, ticker, limit=200, fiscal_period=resolved_period,
    ) if resolved_period else []
    result = compute_change_since(
        price_rows, estimate_rows, since_date=date.fromisoformat(since_date),
    )
    typer.echo(json.dumps({"ticker": ticker, "fiscal_period": resolved_period, **result}))


@analysis_app.command("prepare")
def prepare(ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS):
    """Prepare prior thesis, changes, and current evidence for Codex synthesis."""
    payload = evidence_service.prepare_update(connect(), ticker, max_price_age_days)
    typer.echo(json.dumps(payload))
    if not payload["evidence"]["quality"]["can_research"]:
        raise typer.Exit(code=1)
