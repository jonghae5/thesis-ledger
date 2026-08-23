from src.models.enums import ProviderStatus
from src.providers.alpha_vantage import AlphaVantageEstimateProvider
from src.providers.finnhub import FinnhubNewsProvider
from src.providers.yahoo import YahooPriceProvider


def test_commercial_mode_blocks_unlicensed_market_data(monkeypatch):
    monkeypatch.setenv("THESIS_LEDGER_USAGE", "commercial")
    monkeypatch.delenv("LICENSED_DATA_PROVIDERS", raising=False)

    yahoo = YahooPriceProvider().get_prices("NVDA")
    alpha = AlphaVantageEstimateProvider(api_key="key").get_estimates("NVDA")
    finnhub = FinnhubNewsProvider(api_key="key").get_news("NVDA")

    assert yahoo.status == ProviderStatus.ERROR
    assert alpha.status == ProviderStatus.ERROR
    assert finnhub.status == ProviderStatus.ERROR
    assert "commercial data license" in yahoo.message


def test_personal_mode_keeps_existing_provider_behavior(monkeypatch):
    monkeypatch.setenv("THESIS_LEDGER_USAGE", "personal")
    result = AlphaVantageEstimateProvider(api_key="").get_estimates("NVDA")
    assert result.status == ProviderStatus.SKIPPED
