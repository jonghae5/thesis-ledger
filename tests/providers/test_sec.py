from src.models.enums import ProviderStatus
from src.providers.sec import SecFilingProvider, extract_fundamental_snapshots

TICKERS_JSON = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
}

COMPANY_FACTS_JSON = {
    "cik": 1045810,
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"end": "2025-01-31", "val": 130497000000, "form": "10-K", "fp": "FY", "fy": 2025},
                        {"end": "2026-01-31", "val": 160000000000, "form": "10-K", "fp": "FY", "fy": 2026},
                    ]
                }
            },
            "GrossProfit": {
                "units": {"USD": [{"end": "2026-01-31", "val": 120000000000, "form": "10-K", "fp": "FY", "fy": 2026}]}
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {"USD": [{"end": "2026-01-31", "val": 70000000000, "form": "10-K", "fp": "FY", "fy": 2026}]}
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "units": {"USD": [{"end": "2026-01-31", "val": 3000000000, "form": "10-K", "fp": "FY", "fy": 2026}]}
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"end": "2026-01-31", "start": "2025-02-01", "val": 90000000000, "form": "10-K", "fp": "FY", "fy": 2026},
                        {"end": "2025-10-31", "start": "2025-08-01", "val": 25000000000, "form": "10-K", "fp": "FY", "fy": 2026},
                    ]
                }
            },
        }
    },
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_get_company_facts_returns_ok(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    monkeypatch.setenv("SEC_CONTACT_EMAIL", "research@example.com")

    def fake_get(url, headers=None, timeout=None):
        if "company_tickers.json" in url:
            return _FakeResponse(TICKERS_JSON)
        return _FakeResponse(COMPANY_FACTS_JSON)

    monkeypatch.setattr("src.providers.sec.httpx.get", fake_get)
    result = SecFilingProvider().get_company_facts("NVDA")
    assert result.status == ProviderStatus.OK
    assert result.data["entityName"] == "NVIDIA CORP"


def test_missing_contact_email_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    monkeypatch.delenv("SEC_CONTACT_EMAIL", raising=False)
    result = SecFilingProvider(contact_email="").get_company_facts("NVDA")
    assert result.status == ProviderStatus.ERROR
    assert "SEC_CONTACT_EMAIL not set" in result.message


def test_ticker_directory_failure_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)

    def fail_get(url, headers=None, timeout=None):
        raise RuntimeError("SEC unavailable")

    monkeypatch.setattr("src.providers.sec.httpx.get", fail_get)
    result = SecFilingProvider(contact_email="research@example.com").get_company_facts("NVDA")
    assert result.status == ProviderStatus.ERROR
    assert result.message == "SEC unavailable"


def test_invalid_company_facts_json_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)

    class InvalidJsonResponse(_FakeResponse):
        def json(self):
            raise ValueError("invalid SEC JSON")

    def fake_get(url, headers=None, timeout=None):
        if "company_tickers.json" in url:
            return _FakeResponse(TICKERS_JSON)
        return InvalidJsonResponse(None)

    monkeypatch.setattr("src.providers.sec.httpx.get", fake_get)
    result = SecFilingProvider(contact_email="research@example.com").get_company_facts("NVDA")
    assert result.status == ProviderStatus.ERROR
    assert result.message == "invalid SEC JSON"


def test_unknown_ticker_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)

    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(TICKERS_JSON)

    monkeypatch.setattr("src.providers.sec.httpx.get", fake_get)
    result = SecFilingProvider(contact_email="research@example.com").get_company_facts("NOPE")
    assert result.status == ProviderStatus.ERROR


def test_extract_fundamental_snapshots_uses_actual_filing_date_and_accession():
    payload = {
        "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"start": "2025-02-01", "end": "2026-01-31", "filed": "2026-02-25",
                 "accn": "0001-26-000001", "val": 100.0, "form": "10-K", "fp": "FY", "fy": 2026},
                {"start": "2026-02-01", "end": "2026-05-02", "filed": "2026-05-20",
                 "accn": "0001-26-000002", "val": 30.0, "form": "10-Q", "fp": "Q1", "fy": 2027},
            ]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                {"end": "2026-05-02", "filed": "2026-05-20", "accn": "0001-26-000002",
                 "val": 20.0, "form": "10-Q", "fp": "Q1", "fy": 2027},
            ]}},
        }}
    }

    rows = extract_fundamental_snapshots(payload, "NVDA", "2026-05-21T00:00:00+00:00")

    assert [(r["form"], r["filed_at"], r["period"]) for r in rows] == [
        ("10-K", "2026-02-25", "2026-01-31"),
        ("10-Q", "2026-05-20", "2026-05-02"),
    ]
    assert rows[1]["revenue"] == 30.0
    assert rows[1]["cash"] == 20.0
