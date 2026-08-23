import pytest

from src.tools.portfolio import compute_portfolio_risk, summarize_portfolio

HOLDINGS = [
    {"ticker": "NVDA", "shares": 10.0, "avg_cost": 150.0, "opened_at": "2026-01-15", "sector": "Semiconductors"},
    {"ticker": "AAPL", "shares": 5.0, "avg_cost": 200.0, "opened_at": "2026-02-01", "sector": "Technology"},
]
PRICES = {"NVDA": 214.72, "AAPL": 230.0}


def test_summarize_portfolio_computes_positions_and_weights():
    summary = summarize_portfolio(HOLDINGS, PRICES)
    nvda_value = 10.0 * 214.72
    aapl_value = 5.0 * 230.0
    total = nvda_value + aapl_value

    assert summary["total_market_value"] == pytest.approx(total)
    positions = {p["ticker"]: p for p in summary["positions"]}
    assert positions["NVDA"]["market_value"] == pytest.approx(nvda_value)
    assert positions["NVDA"]["weight"] == pytest.approx(nvda_value / total)
    assert positions["NVDA"]["unrealized_gain_pct"] == pytest.approx((214.72 - 150.0) / 150.0)


def test_summarize_portfolio_ranks_positions_by_weight_descending():
    summary = summarize_portfolio(HOLDINGS, PRICES)
    weights = [p["weight"] for p in summary["positions"]]
    assert weights == sorted(weights, reverse=True)
    assert summary["top_holding_ticker"] == summary["positions"][0]["ticker"]


def test_summarize_portfolio_computes_sector_exposure_with_unknown_bucket():
    holdings = HOLDINGS + [{"ticker": "AMD", "shares": 8.0, "avg_cost": 90.0, "opened_at": "2026-03-01", "sector": None}]
    prices = dict(PRICES, AMD=110.0)
    summary = summarize_portfolio(holdings, prices)

    assert set(summary["sector_exposure"].keys()) == {"Semiconductors", "Technology", "UNKNOWN"}
    amd_weight = next(p["weight"] for p in summary["positions"] if p["ticker"] == "AMD")
    assert summary["sector_exposure"]["UNKNOWN"] == pytest.approx(amd_weight)


def test_summarize_portfolio_raises_when_price_missing():
    with pytest.raises(ValueError):
        summarize_portfolio(HOLDINGS, {"NVDA": 214.72})  # AAPL price missing


def test_summarize_portfolio_raises_on_empty_holdings():
    with pytest.raises(ValueError):
        summarize_portfolio([], {})


def test_compute_portfolio_risk_reports_correlation_beta_and_drawdown():
    positions = summarize_portfolio(HOLDINGS, PRICES)["positions"]
    histories = {}
    for ticker, multiplier in [("NVDA", 1.0), ("AAPL", 0.5)]:
        price = 100.0
        rows = []
        for day in range(30):
            price *= 1 + multiplier * (0.01 if day % 3 else -0.012)
            rows.append({"date": f"2026-07-{day + 1:02d}", "close": price})
        histories[ticker] = rows
    spy = []
    price = 100.0
    for day in range(30):
        price *= 1 + (0.008 if day % 3 else -0.01)
        spy.append({"date": f"2026-07-{day + 1:02d}", "close": price})

    risk = compute_portfolio_risk(positions, histories, benchmark_rows=spy)

    assert risk["status"] == "OK"
    assert risk["observation_count"] == 29
    assert risk["annualized_volatility"] > 0
    assert risk["max_drawdown"] < 0
    assert risk["beta_spy"] is not None
    assert risk["correlations"]["NVDA:AAPL"] == pytest.approx(1.0)
