import json

import typer

from src.cli.common import connect, fail
from src.services.research import (
    DEFAULT_MAX_PRICE_AGE_DAYS,
    latest_price_record,
    reverse_dcf_payload,
    valuation_fundamentals_row,
    valuation_payload,
)
from src.tools.dcf import faded_scenario_metrics, faded_target_price, probability_weighted_value


valuation_app = typer.Typer(help="Run deterministic valuation calculations.")


@valuation_app.command("multiples")
def multiples(ticker: str):
    ticker = ticker.upper()
    try:
        payload = valuation_payload(connect(), ticker)
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@valuation_app.command("reverse-dcf")
def reverse_dcf(
    ticker: str,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
):
    ticker = ticker.upper()
    try:
        payload = reverse_dcf_payload(
            connect(), ticker, discount_rate=discount_rate,
            terminal_growth=terminal_growth, years=years,
        )
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})
    typer.echo(json.dumps(payload))


@valuation_app.command("scenario")
def scenario(
    ticker: str,
    bear_growth: float = typer.Option(...),
    bear_margin: float = typer.Option(...),
    bear_prob: float = typer.Option(...),
    base_growth: float = typer.Option(...),
    base_margin: float = typer.Option(...),
    base_prob: float = typer.Option(...),
    bull_growth: float = typer.Option(...),
    bull_margin: float = typer.Option(...),
    bull_prob: float = typer.Option(...),
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
    annual_dilution: float = typer.Option(..., min=0.0, max=0.999999),
    starting_margin: float | None = typer.Option(
        None,
        "--starting-margin",
        help=(
            "Override the auto-derived trailing FCF margin (USER_ASSUMPTION). "
            "Use when trailing FCF margin is negative or distorted (e.g. a capex supercycle) "
            "and the raw trailing value would otherwise be rejected or misleading."
        ),
    ),
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
):
    ticker = ticker.upper()
    con = connect()
    try:
        fundamentals_row = valuation_fundamentals_row(con, ticker)
        price_row = latest_price_record(con, ticker, max_price_age_days)
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    shares = fundamentals_row.get("shares")
    revenue = fundamentals_row.get("revenue")
    fcf = fundamentals_row.get("fcf")
    debt = fundamentals_row.get("debt")
    cash = fundamentals_row.get("cash")
    if not shares or not revenue or fcf is None or debt is None or cash is None:
        fail({
            "ticker": ticker,
            "status": "ERROR",
            "message": "fundamentals row missing shares/revenue/fcf/debt/cash",
        })
    net_debt = debt - cash
    if starting_margin is not None:
        starting_margin_value = starting_margin
        starting_margin_source = "USER_ASSUMPTION"
    else:
        starting_margin_value = fcf / revenue
        starting_margin_source = fundamentals_row.get("financial_basis")
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
        "starting_fcf_margin": starting_margin_value,
        "starting_fcf_margin_source": starting_margin_source,
        "terminal_growth": terminal_growth,
        "discount_rate": discount_rate,
        "years": years,
        "annual_dilution": annual_dilution,
    }
    scenario_list = []
    try:
        for name, (growth, margin, probability) in cases.items():
            metrics = faded_scenario_metrics(
                revenue, starting_margin_value, growth, margin, shares, net_debt,
                current_price, discount_rate, terminal_growth, years, annual_dilution,
            )
            entry = {
                "probability": probability,
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
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

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
    starting_margin: float | None = typer.Option(
        None,
        "--starting-margin",
        help=(
            "Override the auto-derived trailing FCF margin (USER_ASSUMPTION). "
            "Use when trailing FCF margin is negative or distorted (e.g. a capex supercycle) "
            "and the raw trailing value would otherwise be rejected or misleading."
        ),
    ),
):
    """Return a compact 3x3 faded-growth DCF sensitivity table."""
    ticker = ticker.upper()
    try:
        fundamentals_row = valuation_fundamentals_row(connect(), ticker)
        revenue = fundamentals_row.get("revenue")
        fcf = fundamentals_row.get("fcf")
        shares = fundamentals_row.get("shares")
        debt = fundamentals_row.get("debt")
        cash = fundamentals_row.get("cash")
        if not revenue or fcf is None or not shares or debt is None or cash is None:
            raise ValueError("fundamentals row missing revenue/fcf/shares/debt/cash")
        if starting_margin is not None:
            starting_margin_value = starting_margin
            starting_margin_source = "USER_ASSUMPTION"
        else:
            starting_margin_value = fcf / revenue
            starting_margin_source = fundamentals_row.get("financial_basis")
        growth_values = [growth - growth_step, growth, growth + growth_step]
        discount_values = [discount_rate - discount_step, discount_rate, discount_rate + discount_step]
        matrix = []
        for growth_value in growth_values:
            values = {}
            for rate in discount_values:
                values[f"{rate:.4f}"] = faded_target_price(
                    revenue, starting_margin_value, growth_value, mature_margin,
                    shares, debt - cash, rate, terminal_growth, years, annual_dilution,
                )
            matrix.append({"initial_growth": growth_value, "values_by_discount_rate": values})
    except ValueError as exc:
        fail({"ticker": ticker, "status": "ERROR", "message": str(exc)})

    typer.echo(json.dumps({
        "ticker": ticker,
        "financial_basis": fundamentals_row.get("financial_basis"),
        "starting_fcf_margin": starting_margin_value,
        "starting_fcf_margin_source": starting_margin_source,
        "mature_fcf_margin": mature_margin,
        "terminal_growth": terminal_growth,
        "years": years,
        "annual_dilution": annual_dilution,
        "discount_rates": discount_values,
        "matrix": matrix,
        "source_type": "MODEL_OUTPUT",
    }))
