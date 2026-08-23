from typing import List


def project_enterprise_value(
    base_revenue: float,
    fcf_margin: float,
    growth: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
) -> float:
    if base_revenue <= 0:
        raise ValueError("base_revenue must be positive")
    if growth <= -1:
        raise ValueError("growth must be greater than -1.0")
    if not 0 < discount_rate < 1:
        raise ValueError("discount_rate must be between 0 and 1")
    if not -1 < terminal_growth < 1:
        raise ValueError("terminal_growth must be between -1 and 1")
    if years <= 0:
        raise ValueError("years must be positive")
    if discount_rate <= terminal_growth:
        raise ValueError("discount_rate must be greater than terminal_growth")

    pv = 0.0
    revenue = base_revenue
    fcf = 0.0
    for t in range(1, years + 1):
        revenue *= (1 + growth)
        fcf = revenue * fcf_margin
        pv += fcf / ((1 + discount_rate) ** t)

    terminal_value = fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv += terminal_value / ((1 + discount_rate) ** years)
    return pv


def project_enterprise_value_fade(
    base_revenue: float,
    starting_margin: float,
    initial_growth: float,
    mature_margin: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
) -> float:
    """DCF with growth and FCF margin fading linearly to mature levels."""
    return faded_dcf_breakdown(
        base_revenue, starting_margin, initial_growth, mature_margin,
        discount_rate, terminal_growth, years,
    )["enterprise_value"]


def faded_dcf_breakdown(
    base_revenue: float,
    starting_margin: float,
    initial_growth: float,
    mature_margin: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
) -> dict:
    """Return the faded DCF and the diagnostics an investor needs to audit it."""
    if not 0 <= starting_margin <= 1 or not 0 <= mature_margin <= 1:
        raise ValueError("margins must be between 0 and 1")
    # Reuse the core validation without duplicating its financial constraints.
    project_enterprise_value(
        base_revenue, starting_margin, initial_growth,
        discount_rate, terminal_growth, years,
    )

    revenue = base_revenue
    pv = 0.0
    fcf = 0.0
    for year in range(1, years + 1):
        progress = (year - 1) / (years - 1) if years > 1 else 1.0
        growth = initial_growth + (terminal_growth - initial_growth) * progress
        margin = starting_margin + (mature_margin - starting_margin) * progress
        revenue *= 1 + growth
        fcf = revenue * margin
        pv += fcf / ((1 + discount_rate) ** year)
    terminal_value = fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
    terminal_value_pv = terminal_value / ((1 + discount_rate) ** years)
    enterprise_value = pv + terminal_value_pv
    return {
        "enterprise_value": enterprise_value,
        "explicit_period_pv": pv,
        "terminal_value_pv": terminal_value_pv,
        "terminal_value_pct": terminal_value_pv / enterprise_value if enterprise_value else None,
        "final_year_revenue": revenue,
        "final_year_fcf": fcf,
    }


def faded_target_price(
    base_revenue: float,
    starting_margin: float,
    initial_growth: float,
    mature_margin: float,
    shares: float,
    net_debt: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
    annual_dilution: float = 0.0,
) -> float:
    if shares <= 0:
        raise ValueError("shares must be positive")
    if not 0 <= annual_dilution < 1:
        raise ValueError("annual_dilution must be between 0 and 1")
    enterprise_value = project_enterprise_value_fade(
        base_revenue, starting_margin, initial_growth, mature_margin,
        discount_rate, terminal_growth, years,
    )
    diluted_shares = shares * ((1 + annual_dilution) ** years)
    return max(0.0, (enterprise_value - net_debt) / diluted_shares)


def faded_scenario_metrics(
    base_revenue: float,
    starting_margin: float,
    initial_growth: float,
    mature_margin: float,
    shares: float,
    net_debt: float,
    current_price: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
    annual_dilution: float = 0.0,
) -> dict:
    if shares <= 0 or current_price <= 0:
        raise ValueError("shares and current_price must be positive")
    if not 0 <= annual_dilution < 1:
        raise ValueError("annual_dilution must be between 0 and 1")
    breakdown = faded_dcf_breakdown(
        base_revenue, starting_margin, initial_growth, mature_margin,
        discount_rate, terminal_growth, years,
    )
    diluted_shares = shares * ((1 + annual_dilution) ** years)
    target_price = max(0.0, (breakdown["enterprise_value"] - net_debt) / diluted_shares)
    return {
        "target_price": target_price,
        "upside_downside": target_price / current_price - 1,
        "terminal_value_pct": breakdown["terminal_value_pct"],
        "final_year_revenue": breakdown["final_year_revenue"],
        "final_year_fcf": breakdown["final_year_fcf"],
        "diluted_shares": diluted_shares,
        "cumulative_dilution": diluted_shares / shares - 1,
    }


def implied_growth_rate(
    base_revenue: float,
    fcf_margin: float,
    target_enterprise_value: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
) -> float:
    if fcf_margin <= 0:
        raise ValueError("reverse DCF requires a positive trailing FCF margin")
    if target_enterprise_value <= 0:
        raise ValueError("target_enterprise_value must be positive")

    low, high = -0.9, 5.0
    for _ in range(100):
        mid = (low + high) / 2
        ev = project_enterprise_value(base_revenue, fcf_margin, mid, discount_rate, terminal_growth, years)
        if ev < target_enterprise_value:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def scenario_target_price(
    base_revenue: float,
    fcf_margin: float,
    revenue_growth: float,
    shares: float,
    net_debt: float,
    discount_rate: float = 0.09,
    terminal_growth: float = 0.025,
    years: int = 10,
) -> float:
    if shares <= 0:
        raise ValueError("shares must be positive")
    ev = project_enterprise_value(base_revenue, fcf_margin, revenue_growth, discount_rate, terminal_growth, years)
    market_cap = ev - net_debt
    return market_cap / shares


def probability_weighted_value(scenarios: List[dict]) -> float:
    if not scenarios:
        raise ValueError("at least one scenario is required")
    if any(not 0 <= s["probability"] <= 1 for s in scenarios):
        raise ValueError("scenario probabilities must each be between 0 and 1")
    total_probability = sum(s["probability"] for s in scenarios)
    if abs(total_probability - 1.0) > 1e-6:
        raise ValueError(f"scenario probabilities must sum to 1.0, got {total_probability}")
    return sum(s["probability"] * s["target_price"] for s in scenarios)
