from typing import Optional


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b in (None, 0):
        return None
    return a / b


def compute_forward_multiples(price: float, fundamentals: dict, estimate: Optional[dict]) -> dict:
    shares = fundamentals.get("shares")
    if not shares:
        raise ValueError("fundamentals row has no shares outstanding")

    market_cap = price * shares
    net_debt = None
    if fundamentals.get("debt") is not None and fundamentals.get("cash") is not None:
        net_debt = fundamentals["debt"] - fundamentals["cash"]
    enterprise_value = market_cap + net_debt if net_debt is not None else None

    net_income = fundamentals.get("net_income")
    trailing_pe = _safe_div(price, _safe_div(net_income, shares)) if net_income and net_income > 0 else None
    ev_to_revenue_trailing = _safe_div(enterprise_value, fundamentals.get("revenue"))
    fcf_yield_trailing = _safe_div(fundamentals.get("fcf"), market_cap)

    forward_pe = None
    ev_to_revenue_forward = None
    if estimate:
        eps_mean = estimate.get("eps_mean")
        if eps_mean and eps_mean > 0:
            forward_pe = _safe_div(price, eps_mean)
        ev_to_revenue_forward = _safe_div(enterprise_value, estimate.get("revenue_mean"))

    return {
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "ev_to_revenue_trailing": ev_to_revenue_trailing,
        "ev_to_revenue_forward": ev_to_revenue_forward,
        "fcf_yield_trailing": fcf_yield_trailing,
    }
