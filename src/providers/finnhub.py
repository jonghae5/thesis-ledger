import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from src.models.enums import ProviderStatus
from src.models.schemas import ProviderResult
from src.providers.cache import cached_fetch
from src.providers.policy import commercial_provider_error

FINNHUB_BASE = "https://finnhub.io/api/v1"
CACHE_TTL_SECONDS = 3600


class FinnhubNewsProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.environ.get("FINNHUB_API_KEY", "")

    def get_news(self, ticker: str, days: int = 7, today: Optional[date] = None) -> ProviderResult:
        policy_error = commercial_provider_error("finnhub")
        if policy_error:
            return ProviderResult(status=ProviderStatus.ERROR, message=policy_error)
        if not 1 <= days <= 30:
            return ProviderResult(status=ProviderStatus.ERROR, message="days must be between 1 and 30")
        if not self.api_key:
            return ProviderResult(status=ProviderStatus.SKIPPED, message="FINNHUB_API_KEY not set")

        today = today or date.today()
        from_date = today - timedelta(days=days)

        def _get() -> dict:
            resp = httpx.get(
                f"{FINNHUB_BASE}/company-news",
                params={
                    "symbol": ticker.upper(),
                    "from": from_date.isoformat(),
                    "to": today.isoformat(),
                    "token": self.api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return {"rows": resp.json()}

        cache_key = f"news_{ticker.upper()}_{from_date.isoformat()}_{today.isoformat()}"
        try:
            payload = cached_fetch("finnhub", cache_key, CACHE_TTL_SECONDS, _get)
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))

        return ProviderResult(status=ProviderStatus.OK, data={"rows": parse_company_news(payload["rows"])})


class FinnhubEarningsProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.environ.get("FINNHUB_API_KEY", "")

    def _fetch(self, path: str, cache_key: str, params: dict) -> ProviderResult:
        policy_error = commercial_provider_error("finnhub")
        if policy_error:
            return ProviderResult(status=ProviderStatus.ERROR, message=policy_error)
        if not self.api_key:
            return ProviderResult(status=ProviderStatus.SKIPPED, message="FINNHUB_API_KEY not set")

        def _get() -> dict:
            resp = httpx.get(
                f"{FINNHUB_BASE}/{path}",
                params={**params, "token": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, dict) and body.get("error"):
                raise RuntimeError(str(body["error"]))
            return {"body": body}

        try:
            payload = cached_fetch("finnhub", cache_key, CACHE_TTL_SECONDS, _get)
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        return ProviderResult(status=ProviderStatus.OK, data=payload)

    def get_earnings_history(self, ticker: str) -> ProviderResult:
        result = self._fetch(
            "stock/earnings", f"earnings_{ticker.upper()}",
            {"symbol": ticker.upper(), "limit": 12},
        )
        if result.status != ProviderStatus.OK:
            return result
        rows = parse_finnhub_earnings_surprises(result.data["body"])
        if not rows:
            return ProviderResult(status=ProviderStatus.ERROR, message=f"no Finnhub earnings history for {ticker}")
        return ProviderResult(status=ProviderStatus.OK, data={"rows": rows})

    def get_earnings_calendar(
        self, ticker: str, today: Optional[date] = None, horizon_days: int = 365,
    ) -> ProviderResult:
        today = today or date.today()
        end = today + timedelta(days=horizon_days)
        result = self._fetch(
            "calendar/earnings",
            f"earnings_calendar_{ticker.upper()}_{today.isoformat()}_{end.isoformat()}",
            {"symbol": ticker.upper(), "from": today.isoformat(), "to": end.isoformat()},
        )
        if result.status != ProviderStatus.OK:
            return result
        body = result.data["body"]
        raw_rows = body.get("earningsCalendar", []) if isinstance(body, dict) else []
        rows = parse_finnhub_earnings_calendar(raw_rows)
        if not rows:
            return ProviderResult(status=ProviderStatus.ERROR, message=f"no Finnhub earnings calendar for {ticker}")
        return ProviderResult(status=ProviderStatus.OK, data={"rows": rows})


def parse_company_news(rows: List[Dict[str, Any]]) -> List[dict]:
    parsed = []
    for item in rows:
        parsed.append({
            "headline": item.get("headline"),
            "summary": item.get("summary"),
            "source": item.get("source"),
            "url": item.get("url"),
            "datetime": item.get("datetime"),
            "category": item.get("category"),
        })
    return parsed


def parse_finnhub_earnings_surprises(rows: List[Dict[str, Any]]) -> List[dict]:
    return [{
        "fiscal_date_ending": item.get("period"),
        "reported_date": item.get("period"),
        "reported_eps": item.get("actual"),
        "estimated_eps": item.get("estimate"),
        "surprise": item.get("surprise"),
        "surprise_percentage": item.get("surprisePercent"),
    } for item in rows if item.get("period")]


def parse_finnhub_earnings_calendar(rows: List[Dict[str, Any]]) -> List[dict]:
    return [{
        "symbol": item.get("symbol"),
        "name": None,
        "report_date": item.get("date"),
        "fiscal_date_ending": None,
        "estimate": item.get("epsEstimate"),
        "currency": "USD",
        "time_of_day": item.get("hour"),
    } for item in rows if item.get("date")]
