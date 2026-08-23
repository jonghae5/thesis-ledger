from src.models.enums import ProviderStatus
from src.providers.alpha_vantage import (
    AlphaVantageEstimateProvider,
    parse_earnings_estimates,
    parse_earnings_surprises,
)


def test_get_estimates_returns_skipped_without_key(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    result = AlphaVantageEstimateProvider(api_key="").get_estimates("NVDA")
    assert result.status == ProviderStatus.SKIPPED


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_get_estimates_returns_ok_with_key(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)

    def fake_get(url, params=None, timeout=None):
        return _FakeResponse({"symbol": "NVDA", "annualEarningsEstimates": []})

    monkeypatch.setattr("src.providers.alpha_vantage.httpx.get", fake_get)
    result = AlphaVantageEstimateProvider(api_key="testkey").get_estimates("NVDA")
    assert result.status == ProviderStatus.OK
    assert result.data["symbol"] == "NVDA"


def test_get_estimates_returns_error_on_rate_limit_note(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse({"Note": "rate limit exceeded"})

    monkeypatch.setattr("src.providers.alpha_vantage.httpx.get", fake_get)
    provider = AlphaVantageEstimateProvider(api_key="testkey")
    assert provider.get_estimates("NVDA").status == ProviderStatus.ERROR
    assert provider.get_estimates("NVDA").status == ProviderStatus.ERROR
    assert calls["n"] == 2  # quota errors are never cached


ESTIMATES_PAYLOAD = {
    "symbol": "NVDA",
    "estimates": [
        {
            "date": "2027-01-31", "horizon": "fiscal year",
            "eps_estimate_average": "5.10", "eps_estimate_high": "5.40", "eps_estimate_low": "4.80",
            "eps_estimate_analyst_count": "45",
            "eps_estimate_average_7_days_ago": "5.05",
            "eps_estimate_average_30_days_ago": "4.90",
            "eps_estimate_average_90_days_ago": "4.50",
            "revenue_estimate_average": "220000000000", "revenue_estimate_high": "230000000000",
            "revenue_estimate_low": "210000000000", "revenue_estimate_analyst_count": "42",
            "revenue_estimate_average_7_days_ago": "218000000000",
            "revenue_estimate_average_30_days_ago": "210000000000",
            "revenue_estimate_average_90_days_ago": "200000000000",
        },
        {
            "date": "2026-01-31", "horizon": "fiscal year",
            "eps_estimate_average": "4.20", "eps_estimate_high": "4.50", "eps_estimate_low": "3.90",
            "eps_estimate_analyst_count": "48",
            "revenue_estimate_average": "165000000000", "revenue_estimate_high": "170000000000",
            "revenue_estimate_low": "160000000000", "revenue_estimate_analyst_count": "45",
        },
        {
            "date": "2026-04-30", "horizon": "fiscal quarter",
            "eps_estimate_average": "1.10", "eps_estimate_high": "1.20", "eps_estimate_low": "1.00",
            "eps_estimate_analyst_count": "40",
            "revenue_estimate_average": "45000000000", "revenue_estimate_high": "47000000000",
            "revenue_estimate_low": "43000000000", "revenue_estimate_analyst_count": "38",
        },
    ],
}

EARNINGS_PAYLOAD = {
    "symbol": "NVDA",
    "annualEarnings": [{"fiscalDateEnding": "2026-01-31", "reportedEPS": "4.30"}],
    "quarterlyEarnings": [
        {
            "fiscalDateEnding": "2026-01-31", "reportedDate": "2026-02-20",
            "reportedEPS": "1.15", "estimatedEPS": "1.08",
            "surprise": "0.07", "surprisePercentage": "6.48", "reportTime": "post-market",
        },
        {
            "fiscalDateEnding": "2025-10-31", "reportedDate": "2025-11-19",
            "reportedEPS": "1.05", "estimatedEPS": "1.10",
            "surprise": "-0.05", "surprisePercentage": "-4.55", "reportTime": "post-market",
        },
    ],
}


def test_parse_earnings_estimates_keeps_only_fiscal_year_rows():
    rows = parse_earnings_estimates(ESTIMATES_PAYLOAD)
    assert len(rows) == 2
    assert all(r["date"] in {"2027-01-31", "2026-01-31"} for r in rows)
    next_fy = next(r for r in rows if r["date"] == "2027-01-31")
    assert next_fy["eps_mean"] == 5.10
    assert next_fy["eps_high"] == 5.40
    assert next_fy["eps_low"] == 4.80
    assert next_fy["eps_analyst_count"] == 45
    assert next_fy["revenue_mean"] == 220000000000.0
    assert next_fy["revenue_analyst_count"] == 42
    assert next_fy["eps_mean_7d_ago"] == 5.05
    assert next_fy["eps_mean_30d_ago"] == 4.90
    assert next_fy["eps_mean_90d_ago"] == 4.50
    assert next_fy["revenue_mean_30d_ago"] == 210000000000.0


def test_parse_earnings_surprises_normalizes_quarterly_rows():
    rows = parse_earnings_surprises(EARNINGS_PAYLOAD)
    assert len(rows) == 2
    latest = rows[0]
    assert latest["fiscal_date_ending"] == "2026-01-31"
    assert latest["reported_eps"] == 1.15
    assert latest["estimated_eps"] == 1.08
    assert latest["surprise"] == 0.07
    assert latest["surprise_percentage"] == 6.48


def test_get_earnings_history_returns_skipped_without_key():
    result = AlphaVantageEstimateProvider(api_key="").get_earnings_history("NVDA")
    assert result.status == ProviderStatus.SKIPPED


def test_get_earnings_history_ok_with_key_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(EARNINGS_PAYLOAD)

    monkeypatch.setattr("src.providers.alpha_vantage.httpx.get", fake_get)
    provider = AlphaVantageEstimateProvider(api_key="testkey")
    first = provider.get_earnings_history("NVDA")
    second = provider.get_earnings_history("NVDA")
    assert first.status == ProviderStatus.OK
    assert second.data["symbol"] == "NVDA"
    assert calls["n"] == 1  # second call served from cache


from src.providers.alpha_vantage import parse_earnings_calendar_csv

EARNINGS_CALENDAR_CSV = (
    "symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay\n"
    "NVDA,NVIDIA Corp,2026-11-19,2026-10-31,1.28,USD,post-market\n"
)


def test_parse_earnings_calendar_csv_normalizes_rows():
    rows = parse_earnings_calendar_csv(EARNINGS_CALENDAR_CSV)
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "NVDA"
    assert row["report_date"] == "2026-11-19"
    assert row["fiscal_date_ending"] == "2026-10-31"
    assert row["estimate"] == 1.28
    assert row["time_of_day"] == "post-market"


def test_parse_earnings_calendar_csv_empty_body_returns_empty_list():
    assert parse_earnings_calendar_csv("symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay\n") == []


def test_get_earnings_calendar_returns_skipped_without_key():
    result = AlphaVantageEstimateProvider(api_key="").get_earnings_calendar("NVDA")
    assert result.status == ProviderStatus.SKIPPED


class _FakeTextResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_get_earnings_calendar_ok_with_key_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeTextResponse(EARNINGS_CALENDAR_CSV)

    monkeypatch.setattr("src.providers.alpha_vantage.httpx.get", fake_get)
    provider = AlphaVantageEstimateProvider(api_key="testkey")
    first = provider.get_earnings_calendar("NVDA")
    second = provider.get_earnings_calendar("NVDA")
    assert first.status == ProviderStatus.OK
    assert first.data["rows"][0]["symbol"] == "NVDA"
    assert second.data["rows"][0]["symbol"] == "NVDA"
    assert calls["n"] == 1  # second call served from cache
