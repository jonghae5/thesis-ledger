from src.models.enums import ProviderStatus
from src.providers.finnhub import (
    FinnhubEarningsProvider, FinnhubNewsProvider, parse_company_news,
)


def test_get_news_returns_skipped_without_key():
    result = FinnhubNewsProvider(api_key="").get_news("NVDA")
    assert result.status == ProviderStatus.SKIPPED


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


RAW_NEWS = [
    {
        "headline": "NVIDIA beats estimates",
        "summary": "Strong data center demand.",
        "source": "Reuters",
        "url": "https://example.com/nvda",
        "datetime": 1755878400,
        "category": "company",
    },
]


def test_get_news_ok_with_key_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(RAW_NEWS)

    monkeypatch.setattr("src.providers.finnhub.httpx.get", fake_get)
    provider = FinnhubNewsProvider(api_key="testkey")
    first = provider.get_news("nvda")
    second = provider.get_news("nvda")

    assert first.status == ProviderStatus.OK
    assert first.data["rows"][0]["headline"] == "NVIDIA beats estimates"
    assert second.data["rows"][0]["source"] == "Reuters"
    assert calls["n"] == 1  # second call served from cache


def test_parse_company_news_normalizes_rows():
    rows = parse_company_news(RAW_NEWS)
    assert len(rows) == 1
    assert rows[0]["headline"] == "NVIDIA beats estimates"
    assert rows[0]["url"] == "https://example.com/nvda"


def test_get_earnings_history_normalizes_free_finnhub_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        "src.providers.finnhub.httpx.get",
        lambda *args, **kwargs: _FakeResponse([{
            "actual": 1.1, "estimate": 1.0, "period": "2026-06-30",
            "surprise": 0.1, "surprisePercent": 10.0,
        }]),
    )
    result = FinnhubEarningsProvider(api_key="testkey").get_earnings_history("NVDA")
    assert result.status == ProviderStatus.OK
    assert result.data["rows"][0]["reported_eps"] == 1.1


def test_get_earnings_calendar_normalizes_free_finnhub_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        "src.providers.finnhub.httpx.get",
        lambda *args, **kwargs: _FakeResponse({"earningsCalendar": [{
            "date": "2026-11-19", "epsEstimate": 1.2,
            "hour": "amc", "symbol": "NVDA",
        }]}),
    )
    result = FinnhubEarningsProvider(api_key="testkey").get_earnings_calendar("NVDA")
    assert result.status == ProviderStatus.OK
    assert result.data["rows"][0]["report_date"] == "2026-11-19"
