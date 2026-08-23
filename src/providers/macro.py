import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.models.enums import ProviderStatus
from src.models.schemas import ProviderResult
from src.providers.cache import cached_fetch


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
FRED_CACHE_TTL_SECONDS = 6 * 60 * 60
FEAR_GREED_CACHE_TTL_SECONDS = 10 * 60

# reference_lag is expressed in observations, matching each series' frequency.
FRED_INDICATORS = {
    "REAL_YIELD_10Y": {"series": "DFII10", "unit": "percent", "reference_lag": 20},
    "FED_FUNDS": {"series": "FEDFUNDS", "unit": "percent", "reference_lag": 3},
    "YIELD_CURVE_10Y2Y": {"series": "T10Y2Y", "unit": "percentage_points", "reference_lag": 20},
    "CORE_PCE_YOY": {"series": "PCEPILFE", "unit": "percent_yoy", "reference_lag": 12, "yoy": True},
    "BREAKEVEN_INFLATION_10Y": {"series": "T10YIE", "unit": "percent", "reference_lag": 20},
    "UNEMPLOYMENT_RATE": {"series": "UNRATE", "unit": "percent", "reference_lag": 3},
    "INITIAL_CLAIMS": {"series": "ICSA", "unit": "persons", "reference_lag": 13},
    "SAHM_RULE": {"series": "SAHMREALTIME", "unit": "percentage_points", "reference_lag": 3},
    "HY_OAS": {"series": "BAMLH0A0HYM2", "unit": "percent", "reference_lag": 20},
    "NFCI": {"series": "NFCI", "unit": "index", "reference_lag": 13},
    "VIX": {"series": "VIXCLS", "unit": "index", "reference_lag": 20},
    "TRADE_WEIGHTED_USD": {"series": "DTWEXBGS", "unit": "index", "reference_lag": 20},
}


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "."):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile_5y(observations: list[tuple[date, float]]) -> Optional[float]:
    if not observations:
        return None
    cutoff = observations[-1][0] - timedelta(days=365 * 5)
    window = [value for observation_date, value in observations if observation_date >= cutoff]
    if len(window) < 5:
        window = [value for _, value in observations]
    latest = observations[-1][1]
    return round(sum(value <= latest for value in window) / len(window) * 100, 1)


def _entry_from_observations(
    indicator: str,
    spec: dict,
    observations: list[tuple[date, float]],
    retrieved_at: datetime,
) -> Optional[dict]:
    lag = spec["reference_lag"]
    if len(observations) <= lag:
        return None
    current_date, current_value = observations[-1]
    reference_date, reference_value = observations[-(lag + 1)]
    source_type = "FACT"
    transformation = "LEVEL"
    value = current_value
    percentile_observations = observations
    if spec.get("yoy"):
        transformed = []
        for index in range(lag, len(observations)):
            prior_value = observations[index - lag][1]
            if prior_value != 0:
                transformed.append((
                    observations[index][0],
                    (observations[index][1] / prior_value - 1) * 100,
                ))
        if not transformed:
            return None
        value = transformed[-1][1]
        percentile_observations = transformed
        source_type = "MODEL_OUTPUT"
        transformation = "YOY_PCT"
    return {
        "indicator": indicator,
        "snapshot_at": retrieved_at.isoformat(),
        "observation_date": current_date.isoformat(),
        "value": value,
        "unit": spec["unit"],
        "source_type": source_type,
        "transformation": transformation,
        "reference_date": reference_date.isoformat(),
        "reference_value": reference_value,
        "percentile_5y": _percentile_5y(percentile_observations),
        "source": "fred",
        "source_url": f"https://fred.stlouisfed.org/series/{spec['series']}",
        "retrieved_at": retrieved_at.isoformat(),
    }


def parse_fred_csv(text: str, retrieved_at: datetime) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    date_column = reader.fieldnames[0]
    series_rows: dict[str, list[tuple[date, float]]] = {
        spec["series"]: [] for spec in FRED_INDICATORS.values()
    }
    for raw in reader:
        try:
            observation_date = date.fromisoformat(raw[date_column])
        except (KeyError, TypeError, ValueError):
            continue
        for series_id in series_rows:
            value = _to_float(raw.get(series_id))
            if value is not None:
                series_rows[series_id].append((observation_date, value))

    entries: list[dict] = []
    for indicator, spec in FRED_INDICATORS.items():
        entry = _entry_from_observations(
            indicator, spec, series_rows[spec["series"]], retrieved_at,
        )
        if entry:
            entries.append(entry)
    return entries


class FredMacroProvider:
    def get_snapshot(self, today: Optional[date] = None) -> ProviderResult:
        today = today or date.today()
        start = today - timedelta(days=365 * 6)
        rows = []
        failures = []
        retrieved_at = datetime.now(timezone.utc)
        # trading-agent fetches one fredgraph CSV per series. A multi-series request
        # returns a ZIP split by frequency, so it must not be parsed as plain CSV.
        with httpx.Client(timeout=20) as client:
            for indicator, spec in FRED_INDICATORS.items():
                series_id = spec["series"]

                def _get(series_id=series_id) -> dict:
                    response = client.get(
                        FRED_CSV_URL,
                        params={"id": series_id, "cosd": start.isoformat(), "coed": today.isoformat()},
                    )
                    response.raise_for_status()
                    return {"text": response.text}

                try:
                    payload = cached_fetch(
                        "fred", f"{series_id}_{today.isoformat()}",
                        FRED_CACHE_TTL_SECONDS, _get,
                    )
                    parsed = parse_fred_csv(payload["text"], retrieved_at)
                    row = next((item for item in parsed if item["indicator"] == indicator), None)
                    if row:
                        rows.append(row)
                    else:
                        failures.append(f"{series_id}: insufficient observations")
                except Exception as exc:
                    failures.append(f"{series_id}: {exc}")
        if not rows:
            return ProviderResult(
                status=ProviderStatus.ERROR,
                message="; ".join(failures) or "no usable FRED macro observations",
            )
        return ProviderResult(
            status=ProviderStatus.OK,
            data={"rows": rows, "failures": failures},
            message="; ".join(failures) if failures else None,
        )


class FearGreedProvider:
    def get_snapshot(self, today: Optional[date] = None) -> ProviderResult:
        today = today or date.today()

        def _get() -> dict:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://edition.cnn.com/markets/fear-and-greed",
            }
            response = httpx.get(
                CNN_FEAR_GREED_URL,
                headers=headers,
                timeout=10,
            )
            if response.status_code == 418:
                headers.pop("Referer")
                response = httpx.get(CNN_FEAR_GREED_URL, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()

        try:
            payload = cached_fetch(
                "cnn_fear_greed", f"current_{today.isoformat()}",
                FEAR_GREED_CACHE_TTL_SECONDS, _get,
            )
            current = payload.get("fear_and_greed", {})
            value = _to_float(current.get("score"))
            previous = _to_float(current.get("previous_close"))
            if value is None:
                raise ValueError("CNN response has no fear_and_greed.score")
            retrieved_at = datetime.now(timezone.utc)
            source_timestamp = current.get("timestamp")
            try:
                observation_date = datetime.fromisoformat(
                    str(source_timestamp).replace("Z", "+00:00")
                ).date()
            except (TypeError, ValueError):
                observation_date = today
            row = {
                "indicator": "FEAR_GREED",
                "snapshot_at": retrieved_at.isoformat(),
                "observation_date": observation_date.isoformat(),
                "value": value,
                "unit": "index_0_100",
                "source_type": "FACT",
                "transformation": "LEVEL",
                "reference_date": (observation_date - timedelta(days=1)).isoformat() if previous is not None else None,
                "reference_value": previous,
                "percentile_5y": None,
                "source": "cnn_fear_greed",
                "source_url": CNN_FEAR_GREED_URL,
                "retrieved_at": retrieved_at.isoformat(),
            }
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        return ProviderResult(status=ProviderStatus.OK, data={"rows": [row]})
