import pytest

from src.tools.fundamentals import compute_fundamentals_metrics, compute_ttm_fundamentals


def test_compute_fundamentals_metrics_with_two_periods():
    rows = [
        {"ticker": "NVDA", "period": "2025-01-31", "revenue": 100.0, "gross_profit": 70.0,
         "fcf": 30.0, "cash": 10.0, "debt": 5.0, "shares": 1000.0},
        {"ticker": "NVDA", "period": "2026-01-31", "revenue": 150.0, "gross_profit": 112.5,
         "fcf": 60.0, "cash": 20.0, "debt": 5.0, "shares": 1010.0},
    ]
    metrics = compute_fundamentals_metrics(rows)
    assert metrics["ticker"] == "NVDA"
    assert metrics["period"] == "2026-01-31"
    assert metrics["fcf_margin"] == pytest.approx(60.0 / 150.0)
    assert metrics["net_debt"] == pytest.approx(5.0 - 20.0)
    assert metrics["revenue_growth"] == pytest.approx((150.0 - 100.0) / 100.0)
    assert metrics["gross_margin_change"] == pytest.approx(0.75 - 0.70)
    assert metrics["share_dilution"] == pytest.approx(1010.0 / 1000.0 - 1)


def test_compute_fundamentals_metrics_with_single_period_has_no_deltas():
    rows = [{"ticker": "NVDA", "period": "2026-01-31", "revenue": 150.0, "gross_profit": 112.5,
             "fcf": 60.0, "cash": 20.0, "debt": 5.0, "shares": 1010.0}]
    metrics = compute_fundamentals_metrics(rows)
    assert metrics["revenue_growth"] is None
    assert metrics["gross_margin_change"] is None
    assert metrics["share_dilution"] is None


def test_compute_fundamentals_metrics_raises_on_empty():
    with pytest.raises(ValueError):
        compute_fundamentals_metrics([])


def test_compute_ttm_replaces_new_quarter_and_reports_yoy():
    rows = [
        {"ticker": "AAA", "period": "2025-12-31", "filed_at": "2026-02-15", "form": "10-K",
         "revenue": 400.0, "gross_profit": 200.0, "operating_income": 100.0,
         "net_income": 80.0, "fcf": 60.0, "cash": 30.0, "debt": 10.0, "shares": 100.0},
        {"ticker": "AAA", "period": "2025-03-31", "filed_at": "2026-05-10", "form": "10-Q",
         "revenue": 90.0, "gross_profit": 45.0, "operating_income": 20.0,
         "net_income": 16.0, "fcf": 12.0},
        {"ticker": "AAA", "period": "2026-03-31", "filed_at": "2026-05-10", "form": "10-Q",
         "revenue": 120.0, "gross_profit": 66.0, "operating_income": 30.0,
         "net_income": 24.0, "fcf": 20.0, "cash": 35.0, "debt": 8.0, "shares": 102.0},
    ]

    result = compute_ttm_fundamentals(rows)

    assert result["basis"] == "TTM_DERIVED"
    assert result["filed_at"] == "2026-05-10"
    assert result["quarters_replaced"] == 1
    assert result["revenue"] == pytest.approx(430.0)
    assert result["fcf"] == pytest.approx(68.0)
    assert result["revenue_growth_yoy"] == pytest.approx(120.0 / 90.0 - 1)
    assert result["gross_margin_change_yoy"] == pytest.approx(0.55 - 0.50)
    assert result["net_debt"] == pytest.approx(8.0 - 35.0)


def test_compute_ttm_keeps_missing_flow_null():
    rows = [
        {"ticker": "AAA", "period": "2025-12-31", "filed_at": "2026-02-15", "form": "10-K",
         "revenue": 400.0, "fcf": 60.0},
        {"ticker": "AAA", "period": "2025-03-31", "filed_at": "2026-05-10", "form": "10-Q",
         "revenue": 90.0, "fcf": None},
        {"ticker": "AAA", "period": "2026-03-31", "filed_at": "2026-05-10", "form": "10-Q",
         "revenue": 120.0, "fcf": 20.0},
    ]
    result = compute_ttm_fundamentals(rows)
    assert result["revenue"] == pytest.approx(430.0)
    assert result["fcf"] is None
