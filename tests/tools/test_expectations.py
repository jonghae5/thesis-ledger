from datetime import date

import pytest

from src.tools.expectations import compute_earnings_surprise_summary, select_fiscal_year_estimate

ROWS = [
    {"date": "2027-01-31", "eps_mean": 5.10, "eps_high": 5.40, "eps_low": 4.80, "eps_analyst_count": 45,
     "revenue_mean": 220000000000.0, "revenue_high": 230000000000.0, "revenue_low": 210000000000.0,
     "revenue_analyst_count": 42},
    {"date": "2026-01-31", "eps_mean": 4.20, "eps_high": 4.50, "eps_low": 3.90, "eps_analyst_count": 48,
     "revenue_mean": 165000000000.0, "revenue_high": 170000000000.0, "revenue_low": 160000000000.0,
     "revenue_analyst_count": 45},
]


def test_select_fiscal_year_estimate_current_is_nearest_future_date():
    row = select_fiscal_year_estimate(ROWS, period="current", today=date(2025, 12, 1))
    assert row["date"] == "2026-01-31"


def test_select_fiscal_year_estimate_next_is_the_one_after_current():
    row = select_fiscal_year_estimate(ROWS, period="next", today=date(2025, 12, 1))
    assert row["date"] == "2027-01-31"


def test_select_fiscal_year_estimate_raises_on_empty():
    with pytest.raises(ValueError):
        select_fiscal_year_estimate([], period="current", today=date(2026, 1, 1))


def test_select_fiscal_year_estimate_raises_when_next_unavailable():
    with pytest.raises(ValueError):
        select_fiscal_year_estimate([ROWS[1]], period="next", today=date(2025, 12, 1))


QUARTERLY = [
    {"fiscal_date_ending": "2026-01-31", "reported_eps": 1.15, "estimated_eps": 1.08, "surprise": 0.07, "surprise_percentage": 6.48},
    {"fiscal_date_ending": "2025-10-31", "reported_eps": 1.05, "estimated_eps": 1.10, "surprise": -0.05, "surprise_percentage": -4.55},
    {"fiscal_date_ending": "2025-07-31", "reported_eps": 0.98, "estimated_eps": 0.95, "surprise": 0.03, "surprise_percentage": 3.16},
    {"fiscal_date_ending": "2025-04-30", "reported_eps": 0.90, "estimated_eps": 0.85, "surprise": 0.05, "surprise_percentage": 5.88},
]


def test_compute_earnings_surprise_summary_hit_rate_and_latest():
    summary = compute_earnings_surprise_summary(QUARTERLY)
    assert summary["latest_surprise"] == 0.07
    assert summary["latest_surprise_percentage"] == 6.48
    assert summary["hit_rate_last_4q"] == pytest.approx(0.75)  # 3 of 4 positive surprises


def test_compute_earnings_surprise_summary_raises_on_empty():
    with pytest.raises(ValueError):
        compute_earnings_surprise_summary([])
