import csv
import io
import os
from typing import Any, Dict, List, Optional

import httpx

from src.models.enums import ProviderStatus
from src.models.schemas import ProviderResult
from src.providers.cache import cached_fetch
from src.providers.policy import commercial_provider_error

AV_BASE = "https://www.alphavantage.co/query"
CACHE_TTL_SECONDS = 86400


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    return int(f) if f is not None else None


class AlphaVantageEstimateProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.environ.get("ALPHA_VANTAGE_API_KEY", "")

    def _fetch(self, function: str, ticker: str) -> ProviderResult:
        policy_error = commercial_provider_error("alpha_vantage")
        if policy_error:
            return ProviderResult(status=ProviderStatus.ERROR, message=policy_error)
        if not self.api_key:
            return ProviderResult(status=ProviderStatus.SKIPPED, message="ALPHA_VANTAGE_API_KEY not set")

        def _get() -> dict:
            resp = httpx.get(
                AV_BASE,
                params={"function": function, "symbol": ticker, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            if "Note" in payload or "Information" in payload:
                raise RuntimeError(str(payload.get("Note") or payload.get("Information")))
            return payload

        try:
            payload = cached_fetch("alpha_vantage", f"{function}_{ticker.upper()}", CACHE_TTL_SECONDS, _get)
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))

        if "Note" in payload or "Information" in payload:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(payload.get("Note") or payload.get("Information")))
        return ProviderResult(status=ProviderStatus.OK, data=payload)

    def get_estimates(self, ticker: str) -> ProviderResult:
        return self._fetch("EARNINGS_ESTIMATES", ticker)

    def get_earnings_history(self, ticker: str) -> ProviderResult:
        return self._fetch("EARNINGS", ticker)

    def get_earnings_calendar(self, ticker: str, horizon: str = "12month") -> ProviderResult:
        policy_error = commercial_provider_error("alpha_vantage")
        if policy_error:
            return ProviderResult(status=ProviderStatus.ERROR, message=policy_error)
        if not self.api_key:
            return ProviderResult(status=ProviderStatus.SKIPPED, message="ALPHA_VANTAGE_API_KEY not set")

        def _get() -> dict:
            resp = httpx.get(
                AV_BASE,
                params={"function": "EARNINGS_CALENDAR", "symbol": ticker, "horizon": horizon, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            if not resp.text.lstrip().startswith("symbol,"):
                raise RuntimeError(resp.text.strip() or "invalid Alpha Vantage earnings calendar response")
            return {"rows": parse_earnings_calendar_csv(resp.text)}

        try:
            payload = cached_fetch("alpha_vantage", f"EARNINGS_CALENDAR_{ticker.upper()}", CACHE_TTL_SECONDS, _get)
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        return ProviderResult(status=ProviderStatus.OK, data=payload)


def parse_earnings_estimates(payload: Dict[str, Any]) -> List[dict]:
    rows = []
    for item in payload.get("estimates", []):
        if item.get("horizon") != "fiscal year":
            continue
        rows.append({
            "date": item.get("date"),
            "eps_mean": _to_float(item.get("eps_estimate_average")),
            "eps_high": _to_float(item.get("eps_estimate_high")),
            "eps_low": _to_float(item.get("eps_estimate_low")),
            "eps_analyst_count": _to_int(item.get("eps_estimate_analyst_count")),
            "revenue_mean": _to_float(item.get("revenue_estimate_average")),
            "revenue_high": _to_float(item.get("revenue_estimate_high")),
            "revenue_low": _to_float(item.get("revenue_estimate_low")),
            "revenue_analyst_count": _to_int(item.get("revenue_estimate_analyst_count")),
            # Alpha Vantage includes point-in-time comparison fields in the
            # current response. Preserve them so revisions work on the first
            # fetch instead of waiting 90 days for local snapshots.
            "eps_mean_7d_ago": _to_float(item.get("eps_estimate_average_7_days_ago")),
            "eps_mean_30d_ago": _to_float(item.get("eps_estimate_average_30_days_ago")),
            "eps_mean_90d_ago": _to_float(item.get("eps_estimate_average_90_days_ago")),
            "revenue_mean_7d_ago": _to_float(item.get("revenue_estimate_average_7_days_ago")),
            "revenue_mean_30d_ago": _to_float(item.get("revenue_estimate_average_30_days_ago")),
            "revenue_mean_90d_ago": _to_float(item.get("revenue_estimate_average_90_days_ago")),
        })
    return rows


def parse_earnings_calendar_csv(text: str) -> List[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "report_date": row.get("reportDate"),
            "fiscal_date_ending": row.get("fiscalDateEnding"),
            "estimate": _to_float(row.get("estimate")),
            "currency": row.get("currency"),
            "time_of_day": row.get("timeOfTheDay"),
        })
    return rows


def parse_earnings_surprises(payload: Dict[str, Any]) -> List[dict]:
    rows = []
    for item in payload.get("quarterlyEarnings", []):
        rows.append({
            "fiscal_date_ending": item.get("fiscalDateEnding"),
            "reported_date": item.get("reportedDate"),
            "reported_eps": _to_float(item.get("reportedEPS")),
            "estimated_eps": _to_float(item.get("estimatedEPS")),
            "surprise": _to_float(item.get("surprise")),
            "surprise_percentage": _to_float(item.get("surprisePercentage")),
        })
    return rows
