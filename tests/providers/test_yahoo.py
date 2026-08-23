import pandas as pd
import pytest

from src.models.enums import ProviderStatus
from src.providers.yahoo import YahooEstimateProvider, YahooPriceProvider, parse_yahoo_earnings_dates


class _FakeTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, period):
        idx = pd.to_datetime(["2026-08-20", "2026-08-21"])
        return pd.DataFrame(
            {"Open": [100.0, 102.0], "High": [103.0, 105.0], "Low": [99.0, 101.0],
             "Close": [102.0, 104.0], "Volume": [1000, 1200]},
            index=idx,
        )


def test_get_prices_returns_ok_with_rows(monkeypatch):
    monkeypatch.setattr("src.providers.yahoo.yf.Ticker", _FakeTicker)
    result = YahooPriceProvider().get_prices("NVDA", period_days=10)
    assert result.status == ProviderStatus.OK
    rows = result.data["rows"]
    assert len(rows) == 2
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["date"] == "2026-08-20"
    assert rows[0]["source"] == "yahoo_finance"
    assert rows[1]["close"] == 104.0


class _EmptyTicker:
    def history(self, period):
        return pd.DataFrame()


def test_get_prices_returns_error_when_empty(monkeypatch):
    monkeypatch.setattr("src.providers.yahoo.yf.Ticker", lambda t: _EmptyTicker())
    result = YahooPriceProvider().get_prices("BADTICKER")
    assert result.status == ProviderStatus.ERROR


class _AnalysisTicker:
    def get_earnings_estimate(self):
        return pd.DataFrame({
            "numberOfAnalysts": [40, 35], "avg": [5.0, 6.0],
            "low": [4.5, 5.5], "high": [5.5, 6.5],
        }, index=["0y", "+1y"])

    def get_revenue_estimate(self):
        return pd.DataFrame({
            "numberOfAnalysts": [38, 32], "avg": [100.0, 120.0],
            "low": [90.0, 110.0], "high": [110.0, 130.0],
        }, index=["0y", "+1y"])


def test_get_estimates_normalizes_yahoo_analysis(monkeypatch):
    monkeypatch.setattr("src.providers.yahoo.yf.Ticker", lambda ticker: _AnalysisTicker())
    result = YahooEstimateProvider().get_estimates("NVDA")
    assert result.status == ProviderStatus.OK
    assert result.data["rows"][0]["period"] == "0y"
    assert result.data["rows"][0]["eps_mean"] == 5.0
    assert result.data["rows"][1]["revenue_high"] == 130.0


def test_parse_yahoo_earnings_dates_separates_history_and_calendar():
    idx = pd.to_datetime(["2026-08-20", "2026-11-20"], utc=True)
    frame = pd.DataFrame({
        "EPS Estimate": [1.0, 1.2], "Reported EPS": [1.1, float("nan")],
        "Surprise(%)": [10.0, float("nan")],
    }, index=idx)
    history, calendar = parse_yahoo_earnings_dates(frame, today=pd.Timestamp("2026-08-23").date())
    assert history[0]["surprise"] == pytest.approx(0.1)
    assert calendar[0]["report_date"] == "2026-11-20"
