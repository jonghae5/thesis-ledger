from datetime import date
from typing import Optional


GROUPS = {
    "rates": ("FED_FUNDS", "REAL_YIELD_10Y", "YIELD_CURVE_10Y2Y"),
    "inflation": ("CORE_PCE_YOY", "BREAKEVEN_INFLATION_10Y"),
    "growth_labor": ("UNEMPLOYMENT_RATE", "INITIAL_CLAIMS", "SAHM_RULE"),
    "credit_liquidity": ("HY_OAS", "NFCI"),
    "sentiment_stress": ("VIX", "FEAR_GREED"),
    "currency": ("TRADE_WEIGHTED_USD",),
}

CORE_INDICATORS = {
    "FED_FUNDS", "REAL_YIELD_10Y", "YIELD_CURVE_10Y2Y",
    "CORE_PCE_YOY", "BREAKEVEN_INFLATION_10Y",
    "UNEMPLOYMENT_RATE", "INITIAL_CLAIMS", "SAHM_RULE", "HY_OAS", "NFCI", "VIX",
}

MAX_OBSERVATION_AGE_DAYS = {
    "REAL_YIELD_10Y": 7, "YIELD_CURVE_10Y2Y": 7, "BREAKEVEN_INFLATION_10Y": 7,
    "HY_OAS": 7, "VIX": 7,
    "TRADE_WEIGHTED_USD": 14, "FEAR_GREED": 2,
    "INITIAL_CLAIMS": 14, "NFCI": 14,
    # Monthly observations are dated at period start and released later, so 95
    # days avoids marking a normally published latest month as stale.
    "FED_FUNDS": 95, "CORE_PCE_YOY": 95, "UNEMPLOYMENT_RATE": 95, "SAHM_RULE": 95,
}


def _direction(row: dict) -> Optional[str]:
    reference = row.get("reference_value")
    if reference is None or row["transformation"] == "YOY_PCT":
        return None
    change = row["value"] - reference
    tolerance = max(abs(reference) * 0.01, 0.01)
    if change > tolerance:
        return "RISING"
    if change < -tolerance:
        return "FALLING"
    return "STABLE"


def _state(indicator: str, value: float) -> Optional[str]:
    if indicator == "VIX":
        return "EXTREME_STRESS" if value >= 30 else "STRESS" if value >= 25 else "CALM" if value < 15 else "NORMAL"
    if indicator == "FEAR_GREED":
        return "EXTREME_FEAR" if value <= 25 else "FEAR" if value <= 45 else "NEUTRAL" if value <= 55 else "GREED" if value <= 75 else "EXTREME_GREED"
    if indicator == "SAHM_RULE":
        return "RECESSION_TRIGGERED" if value >= 0.5 else "WATCH" if value >= 0.3 else "BELOW_TRIGGER"
    if indicator == "NFCI":
        return "TIGHTER_THAN_AVERAGE" if value > 0 else "LOOSER_THAN_AVERAGE"
    if indicator == "HY_OAS":
        return "SEVERE_STRESS" if value >= 7 else "ELEVATED" if value >= 5 else "NORMAL"
    if indicator == "YIELD_CURVE_10Y2Y":
        return "INVERTED" if value < 0 else "POSITIVE"
    return None


def build_macro_context(rows: list[dict], as_of: Optional[date] = None) -> dict:
    by_indicator = {row["indicator"]: row for row in rows}
    missing_core = sorted(CORE_INDICATORS - set(by_indicator))
    effective_date = as_of or date.today()
    stale = sorted(
        indicator for indicator, row in by_indicator.items()
        if indicator in MAX_OBSERVATION_AGE_DAYS
        and (effective_date - date.fromisoformat(row["observation_date"])).days
        > MAX_OBSERVATION_AGE_DAYS[indicator]
    )
    stale_core = sorted(CORE_INDICATORS.intersection(stale))
    groups = {}
    for group, indicators in GROUPS.items():
        values = {}
        for indicator in indicators:
            row = by_indicator.get(indicator)
            if not row:
                continue
            reference = row.get("reference_value")
            values[indicator] = {
                "value": row["value"],
                "unit": row["unit"],
                "observation_date": row["observation_date"],
                "snapshot_at": row["snapshot_at"],
                "source_type": row["source_type"],
                "transformation": row["transformation"],
                "reference_date": row.get("reference_date"),
                "reference_value": reference,
                "change": row["value"] - reference if reference is not None and row["transformation"] != "YOY_PCT" else None,
                "direction": _direction(row),
                "state": _state(indicator, row["value"]),
                "percentile_5y": row.get("percentile_5y"),
                "provenance": {
                    "source": row["source"],
                    "source_url": row.get("source_url"),
                    "retrieved_at": row["retrieved_at"],
                },
            }
        groups[group] = values

    warnings = []
    if "FEAR_GREED" not in by_indicator:
        warnings.append("Fear & Greed unavailable; sentiment context is limited to VIX")
    if missing_core:
        warnings.append(f"missing core macro indicators: {', '.join(missing_core)}")
    if stale:
        warnings.append(f"stale macro indicators: {', '.join(stale)}")
    return {
        "status": "MISSING" if not rows else ("PARTIAL" if missing_core or stale_core else "OK"),
        "as_of_date": effective_date.isoformat(),
        "source_type": "FACT_AND_MODEL_OUTPUT",
        "groups": groups,
        "missing_core": missing_core,
        "stale": stale,
        "warnings": warnings,
        "interpretation_rule": (
            "Use macro indicators as scenario and position-sizing context; "
            "Fear & Greed is secondary sentiment evidence, not intrinsic value or a buy/sell signal."
        ),
    }
