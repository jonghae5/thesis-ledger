import pytest

from src.tools.valuation import compute_forward_multiples

FUNDAMENTALS = {
    "ticker": "NVDA", "period": "2026-01-25",
    "revenue": 215938000000.0, "gross_profit": 153463000000.0,
    "operating_income": 100000000000.0, "net_income": 90000000000.0,
    "fcf": 95000000000.0, "cash": 7469000000.0, "debt": 8463000000.0,
    "shares": 24304000000.0,
}

ESTIMATE = {"eps_mean": 5.10, "revenue_mean": 260000000000.0}


def test_compute_forward_multiples_with_consensus():
    metrics = compute_forward_multiples(price=200.0, fundamentals=FUNDAMENTALS, estimate=ESTIMATE)
    shares = FUNDAMENTALS["shares"]
    market_cap = 200.0 * shares
    net_debt = FUNDAMENTALS["debt"] - FUNDAMENTALS["cash"]
    ev = market_cap + net_debt

    assert metrics["market_cap"] == pytest.approx(market_cap)
    assert metrics["enterprise_value"] == pytest.approx(ev)
    assert metrics["trailing_pe"] == pytest.approx(200.0 / (FUNDAMENTALS["net_income"] / shares))
    assert metrics["forward_pe"] == pytest.approx(200.0 / ESTIMATE["eps_mean"])
    assert metrics["ev_to_revenue_trailing"] == pytest.approx(ev / FUNDAMENTALS["revenue"])
    assert metrics["ev_to_revenue_forward"] == pytest.approx(ev / ESTIMATE["revenue_mean"])
    assert metrics["fcf_yield_trailing"] == pytest.approx(FUNDAMENTALS["fcf"] / market_cap)


def test_compute_forward_multiples_without_consensus_omits_forward_fields():
    metrics = compute_forward_multiples(price=200.0, fundamentals=FUNDAMENTALS, estimate=None)
    assert metrics["forward_pe"] is None
    assert metrics["ev_to_revenue_forward"] is None
    assert metrics["trailing_pe"] is not None


def test_compute_forward_multiples_raises_without_shares():
    bad = dict(FUNDAMENTALS)
    bad["shares"] = None
    with pytest.raises(ValueError):
        compute_forward_multiples(price=200.0, fundamentals=bad, estimate=None)


def test_compute_forward_multiples_handles_negative_net_income():
    bad = dict(FUNDAMENTALS)
    bad["net_income"] = -1000000000.0
    metrics = compute_forward_multiples(price=200.0, fundamentals=bad, estimate=None)
    assert metrics["trailing_pe"] is None  # P/E undefined for negative earnings
