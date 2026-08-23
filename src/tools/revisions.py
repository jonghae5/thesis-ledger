from datetime import datetime, timedelta, timezone
from typing import List, Optional


def _as_aware_utc(dt: datetime) -> datetime:
    """DuckDB TIMESTAMP columns drop tzinfo on round-trip; snapshots are
    always written in UTC (see cli/main.py), so a naive value is UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _closest_at_or_before(snapshots: List[dict], target_time: datetime) -> Optional[dict]:
    target_time = _as_aware_utc(target_time)
    candidates = [
        s for s in snapshots
        if _as_aware_utc(datetime.fromisoformat(s["snapshot_at"])) <= target_time
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s["snapshot_at"])


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old


def compute_revision_metrics(snapshots: List[dict], now: datetime) -> dict:
    if not snapshots:
        raise ValueError("no estimate snapshots")

    fiscal_periods = {s.get("fiscal_period") for s in snapshots if s.get("fiscal_period") is not None}
    if len(fiscal_periods) > 1:
        raise ValueError("revision snapshots must belong to exactly one fiscal period")

    ordered = sorted(snapshots, key=lambda s: s["snapshot_at"])
    latest_source = ordered[-1].get("source")
    sources = {s.get("source") for s in ordered if s.get("source") is not None}
    provider_switch = len(sources) > 1
    if latest_source is not None:
        ordered = [s for s in ordered if s.get("source") == latest_source]
    latest = ordered[-1]

    windows = {"7d": 7, "30d": 30, "90d": 90}
    eps_revisions = {}
    revenue_revisions = {}
    for label, days in windows.items():
        baseline = _closest_at_or_before(ordered[:-1], now - timedelta(days=days))
        eps_provider_baseline = latest.get(f"eps_mean_{label}_ago")
        revenue_provider_baseline = latest.get(f"revenue_mean_{label}_ago")
        eps_revisions[label] = (
            _pct_change(latest.get("eps_mean"), eps_provider_baseline)
            if eps_provider_baseline is not None
            else (_pct_change(latest.get("eps_mean"), baseline.get("eps_mean")) if baseline else None)
        )
        revenue_revisions[label] = (
            _pct_change(latest.get("revenue_mean"), revenue_provider_baseline)
            if revenue_provider_baseline is not None
            else (_pct_change(latest.get("revenue_mean"), baseline.get("revenue_mean")) if baseline else None)
        )

    earliest = ordered[0]
    analyst_count_change = None
    if latest.get("analyst_count") is not None and earliest.get("analyst_count") is not None:
        analyst_count_change = latest["analyst_count"] - earliest["analyst_count"]

    weights = {"7d": 0.5, "30d": 0.3, "90d": 0.2}
    available = {k: v for k, v in eps_revisions.items() if v is not None}
    revision_score = None
    if available:
        weight_sum = sum(weights[k] for k in available)
        weighted = sum(weights[k] * v for k, v in available.items()) / weight_sum
        revision_score = max(-1.0, min(1.0, weighted))

    revision_acceleration = None
    if all(eps_revisions[k] is not None for k in windows):
        signs = {(1 if eps_revisions[k] > 0 else (-1 if eps_revisions[k] < 0 else 0)) for k in windows}
        revision_acceleration = len(signs) == 1

    return {
        "fiscal_period": next(iter(fiscal_periods), None),
        "provider": latest_source,
        "provider_switch": provider_switch,
        "revision_source": (
            "PROVIDER_HISTORY"
            if any(latest.get(f"eps_mean_{label}_ago") is not None for label in windows)
            else "LOCAL_SNAPSHOTS"
        ),
        "eps_revision_7d": eps_revisions["7d"],
        "eps_revision_30d": eps_revisions["30d"],
        "eps_revision_90d": eps_revisions["90d"],
        "revenue_revision_7d": revenue_revisions["7d"],
        "revenue_revision_30d": revenue_revisions["30d"],
        "revenue_revision_90d": revenue_revisions["90d"],
        "analyst_count_change": analyst_count_change,
        "revision_score": revision_score,
        "revision_acceleration": revision_acceleration,
    }
