from datetime import date, datetime, timezone

from src.models.enums import ProviderStatus
from src.providers.macro import FearGreedProvider, parse_fred_csv


def test_parse_fred_csv_builds_levels_and_core_pce_yoy():
    headers = [
        "DATE", "DFII10", "FEDFUNDS", "T10Y2Y", "PCEPILFE", "T10YIE", "UNRATE", "ICSA",
        "SAHMREALTIME", "BAMLH0A0HYM2", "NFCI", "VIXCLS", "DTWEXBGS",
    ]
    lines = [",".join(headers)]
    for index in range(25):
        values = [
            date(2024, 1, 1).replace(day=min(index + 1, 28)).isoformat(),
            str(1 + index / 100), str(5 - index / 100), str(-0.5 + index / 100),
            str(100 + index), str(2 + index / 100),
            str(4 + index / 100), str(200000 + index), str(index / 100),
            str(3 + index / 100), str(-0.5 + index / 100), str(15 + index / 10),
            str(100 + index / 10),
        ]
        lines.append(",".join(values))

    rows = parse_fred_csv("\n".join(lines), datetime(2024, 2, 1, tzinfo=timezone.utc))
    by_indicator = {row["indicator"]: row for row in rows}

    assert set(by_indicator) == {
        "REAL_YIELD_10Y", "FED_FUNDS", "YIELD_CURVE_10Y2Y", "CORE_PCE_YOY",
        "BREAKEVEN_INFLATION_10Y",
        "UNEMPLOYMENT_RATE", "INITIAL_CLAIMS", "SAHM_RULE", "HY_OAS",
        "NFCI", "VIX", "TRADE_WEIGHTED_USD",
    }
    assert by_indicator["REAL_YIELD_10Y"]["source_type"] == "FACT"
    assert by_indicator["CORE_PCE_YOY"]["source_type"] == "MODEL_OUTPUT"
    assert by_indicator["CORE_PCE_YOY"]["transformation"] == "YOY_PCT"
    assert 0 <= by_indicator["CORE_PCE_YOY"]["percentile_5y"] <= 100


def test_fear_greed_provider_parses_current_and_previous(monkeypatch):
    monkeypatch.setattr(
        "src.providers.macro.cached_fetch",
        lambda *args, **kwargs: {"fear_and_greed": {
            "score": 18.4, "previous_close": 22.0,
            "timestamp": "2026-08-21T23:59:58+00:00",
        }},
    )

    result = FearGreedProvider().get_snapshot(today=date(2026, 8, 23))

    assert result.status == ProviderStatus.OK
    row = result.data["rows"][0]
    assert row["indicator"] == "FEAR_GREED"
    assert row["value"] == 18.4
    assert row["reference_value"] == 22.0
    assert row["observation_date"] == "2026-08-21"
