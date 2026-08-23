from datetime import date

from src.tools.macro import build_macro_context


def _row(indicator, value, reference=10.0):
    return {
        "indicator": indicator, "value": value, "reference_value": reference,
        "reference_date": "2026-07-23", "observation_date": "2026-08-23",
        "snapshot_at": "2026-08-23T12:00:00+00:00", "retrieved_at": "2026-08-23T12:00:00+00:00",
        "unit": "index", "source_type": "FACT", "transformation": "LEVEL",
        "source": "test", "source_url": None,
    }


def test_macro_context_keeps_axes_separate_and_classifies_sentiment():
    rows = [
        _row("VIX", 31.0, 20.0),
        _row("FEAR_GREED", 19.0, 25.0),
        _row("SAHM_RULE", 0.51, 0.2),
        _row("NFCI", 0.2, -0.1),
        _row("HY_OAS", 5.5, 4.0),
    ]

    result = build_macro_context(rows, as_of=date(2026, 8, 23))

    assert result["status"] == "PARTIAL"
    assert result["groups"]["sentiment_stress"]["VIX"]["state"] == "EXTREME_STRESS"
    assert result["groups"]["sentiment_stress"]["FEAR_GREED"]["state"] == "EXTREME_FEAR"
    assert "score" not in result


def test_macro_context_missing_is_explicit():
    result = build_macro_context([])
    assert result["status"] == "MISSING"
    assert result["missing_core"]


def test_macro_context_marks_stale_core_data_partial():
    rows = [_row("VIX", 18.0, 17.0)]
    rows[0]["observation_date"] = "2026-07-01"
    result = build_macro_context(rows, as_of=date(2026, 8, 23))
    assert result["status"] == "PARTIAL"
    assert result["stale"] == ["VIX"]
