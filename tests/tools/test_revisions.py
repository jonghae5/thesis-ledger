from datetime import datetime, timedelta, timezone

import pytest

from src.tools.revisions import compute_revision_metrics

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def _snap(days_ago, eps, revenue, analysts):
    return {
        "snapshot_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "eps_mean": eps, "revenue_mean": revenue, "analyst_count": analysts,
    }


def test_compute_revision_metrics_with_full_history():
    snapshots = [
        _snap(95, 4.00, 160000.0, 40),
        _snap(32, 4.10, 162000.0, 42),
        _snap(8, 4.15, 163000.0, 43),
        _snap(0, 4.20, 165000.0, 45),
    ]
    metrics = compute_revision_metrics(snapshots, now=NOW)
    assert metrics["eps_revision_90d"] == pytest.approx((4.20 - 4.00) / 4.00)
    assert metrics["eps_revision_30d"] == pytest.approx((4.20 - 4.10) / 4.10)
    assert metrics["eps_revision_7d"] == pytest.approx((4.20 - 4.15) / 4.15)
    assert metrics["revenue_revision_90d"] == pytest.approx((165000.0 - 160000.0) / 160000.0)
    assert metrics["analyst_count_change"] == 45 - 40
    assert metrics["revision_score"] is not None
    assert -1.0 <= metrics["revision_score"] <= 1.0
    assert metrics["revision_acceleration"] is True  # all three windows positive


def test_compute_revision_metrics_with_single_snapshot_returns_nulls():
    metrics = compute_revision_metrics([_snap(0, 4.20, 165000.0, 45)], now=NOW)
    assert metrics["eps_revision_7d"] is None
    assert metrics["eps_revision_30d"] is None
    assert metrics["eps_revision_90d"] is None
    assert metrics["revision_score"] is None
    assert metrics["revision_acceleration"] is None


def test_compute_revision_metrics_uses_provider_history_on_first_fetch():
    latest = _snap(0, 4.20, 165000.0, 45)
    latest.update({
        "eps_mean_7d_ago": 4.15,
        "eps_mean_30d_ago": 4.10,
        "eps_mean_90d_ago": 4.00,
        "revenue_mean_7d_ago": 164000.0,
        "revenue_mean_30d_ago": 162000.0,
        "revenue_mean_90d_ago": 160000.0,
    })

    metrics = compute_revision_metrics([latest], now=NOW)

    assert metrics["revision_source"] == "PROVIDER_HISTORY"
    assert metrics["eps_revision_30d"] == pytest.approx((4.20 - 4.10) / 4.10)
    assert metrics["revenue_revision_90d"] == pytest.approx((165000.0 - 160000.0) / 160000.0)
    assert metrics["revision_score"] is not None


def test_compute_revision_metrics_raises_on_empty():
    with pytest.raises(ValueError):
        compute_revision_metrics([], now=NOW)


def test_compute_revision_metrics_mixed_sign_is_not_accelerating():
    snapshots = [
        _snap(95, 4.00, 160000.0, 40),
        _snap(32, 4.30, 162000.0, 42),  # 30d revision positive
        _snap(8, 4.10, 163000.0, 43),   # but 7d revision negative vs current
        _snap(0, 4.05, 165000.0, 45),
    ]
    metrics = compute_revision_metrics(snapshots, now=NOW)
    assert metrics["revision_acceleration"] is False


def test_compute_revision_metrics_rejects_mixed_fiscal_periods():
    snapshots = [
        {**_snap(7, 4.0, 160000.0, 40), "fiscal_period": "2027-01-31"},
        {**_snap(0, 5.0, 180000.0, 42), "fiscal_period": "2028-01-31"},
    ]
    with pytest.raises(ValueError, match="exactly one fiscal period"):
        compute_revision_metrics(snapshots, now=NOW)


def test_compute_revision_metrics_does_not_compare_across_provider_switch():
    snapshots = [
        {**_snap(30, 4.0, 160000.0, 40), "source": "alpha_vantage"},
        {**_snap(0, 5.0, 180000.0, 42), "source": "yahoo_finance"},
    ]
    metrics = compute_revision_metrics(snapshots, now=NOW)
    assert metrics["provider_switch"] is True
    assert metrics["provider"] == "yahoo_finance"
    assert metrics["eps_revision_30d"] is None
    assert metrics["revision_score"] is None
