import pytest

from src.tools.market import compute_market_metrics


def _rows(closes):
    return [
        {"ticker": "NVDA", "date": f"2026-01-{i+1:02d}" if i < 28 else f"2026-02-{i-27:02d}",
         "open": c, "high": c, "low": c, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ]


def test_compute_market_metrics_basic_momentum():
    closes = [100.0] * 20 + [110.0] * 5  # 25 days, last close 110
    rows = _rows(closes)
    metrics = compute_market_metrics("NVDA", rows)
    assert metrics["ticker"] == "NVDA"
    assert metrics["price"] == 110.0
    assert metrics["source_type"] == "MODEL_OUTPUT"


def test_compute_market_metrics_raises_on_empty_rows():
    with pytest.raises(ValueError):
        compute_market_metrics("NVDA", [])


def test_relative_strength_uses_spy_rows_when_given():
    closes = [100.0] * 20 + [x for x in range(101, 106)]
    rows = _rows(closes)
    spy_rows = _rows([100.0] * 25)
    metrics = compute_market_metrics("NVDA", rows, spy_rows=spy_rows)
    assert metrics["relative_strength_spy"] is not None
