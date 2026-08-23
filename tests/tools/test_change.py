from datetime import date

import pytest

from src.tools.change import compute_change_since


def _price(d, close):
    return {"date": d, "close": close}


def _snapshot(dt, eps, revenue):
    return {"snapshot_at": dt, "eps_mean": eps, "revenue_mean": revenue}


def test_compute_change_since_with_full_history():
    price_rows = [_price("2026-07-01", 180.0), _price("2026-07-22", 195.0), _price("2026-08-22", 214.72)]
    estimate_rows = [
        _snapshot("2026-07-01T00:00:00+00:00", 4.00, 160000.0),
        _snapshot("2026-08-22T00:00:00+00:00", 4.20, 165000.0),
    ]
    result = compute_change_since(price_rows, estimate_rows, since_date=date(2026, 7, 22))
    assert result["since_date"] == "2026-07-22"
    assert result["price_then"] == 195.0
    assert result["price_now"] == 214.72
    assert result["price_change_pct"] == pytest.approx((214.72 - 195.0) / 195.0)
    assert result["eps_then"] == 4.00  # closest snapshot at-or-before 2026-07-22 is the 07-01 one
    assert result["eps_now"] == 4.20
    assert result["eps_change_pct"] == pytest.approx((4.20 - 4.00) / 4.00)
    assert result["revenue_change_pct"] == pytest.approx((165000.0 - 160000.0) / 160000.0)


def test_compute_change_since_with_no_price_before_since_date_returns_null_then():
    price_rows = [_price("2026-08-01", 200.0), _price("2026-08-22", 214.72)]
    result = compute_change_since(price_rows, [], since_date=date(2026, 1, 1))
    assert result["price_then"] is None
    assert result["price_change_pct"] is None
    assert result["price_now"] == 214.72


def test_compute_change_since_with_no_estimate_rows_returns_null_eps_fields():
    price_rows = [_price("2026-08-01", 200.0), _price("2026-08-22", 214.72)]
    result = compute_change_since(price_rows, [], since_date=date(2026, 8, 1))
    assert result["eps_then"] is None
    assert result["eps_now"] is None
    assert result["eps_change_pct"] is None


def test_compute_change_since_raises_on_empty_price_rows():
    with pytest.raises(ValueError):
        compute_change_since([], [], since_date=date(2026, 8, 1))
