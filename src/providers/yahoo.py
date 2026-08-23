from datetime import date, datetime, timezone
from math import isnan
from typing import Any, Optional

import yfinance as yf

from src.models.enums import ProviderStatus
from src.models.schemas import ProviderResult
from src.providers.policy import commercial_provider_error


class YahooPriceProvider:
    def get_prices(self, ticker: str, period_days: int = 400) -> ProviderResult:
        policy_error = commercial_provider_error("yahoo_finance")
        if policy_error:
            return ProviderResult(status=ProviderStatus.ERROR, message=policy_error)
        try:
            hist = yf.Ticker(ticker).history(period=f"{period_days}d")
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))

        if hist.empty:
            return ProviderResult(status=ProviderStatus.ERROR, message=f"no price data for {ticker}")

        retrieved_at = datetime.now(timezone.utc).isoformat()
        rows = []
        for idx, row in hist.iterrows():
            d = idx.date().isoformat()
            rows.append({
                "ticker": ticker,
                "date": d,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
                "source": "yahoo_finance",
                "source_url": f"https://finance.yahoo.com/quote/{ticker}",
                "retrieved_at": retrieved_at,
                "as_of_date": d,
            })
        return ProviderResult(status=ProviderStatus.OK, data={"rows": rows})


def _optional_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if isnan(number) else number


def _optional_int(value: Any) -> Optional[int]:
    number = _optional_number(value)
    return int(number) if number is not None else None


def parse_yahoo_estimates(earnings, revenue) -> list[dict]:
    rows = []
    for period in ("0y", "+1y"):
        if period not in earnings.index or period not in revenue.index:
            continue
        eps = earnings.loc[period]
        sales = revenue.loc[period]
        rows.append({
            "period": period,
            "eps_mean": _optional_number(eps.get("avg")),
            "eps_high": _optional_number(eps.get("high")),
            "eps_low": _optional_number(eps.get("low")),
            "eps_analyst_count": _optional_int(eps.get("numberOfAnalysts")),
            "revenue_mean": _optional_number(sales.get("avg")),
            "revenue_high": _optional_number(sales.get("high")),
            "revenue_low": _optional_number(sales.get("low")),
            "revenue_analyst_count": _optional_int(sales.get("numberOfAnalysts")),
        })
    return rows


def parse_yahoo_earnings_dates(frame, today: Optional[date] = None) -> tuple[list[dict], list[dict]]:
    today = today or date.today()
    surprises = []
    calendar = []
    if frame is None or frame.empty:
        return surprises, calendar
    for idx, row in frame.iterrows():
        event_date = idx.date()
        estimate = _optional_number(row.get("EPS Estimate"))
        reported = _optional_number(row.get("Reported EPS"))
        surprise_pct = _optional_number(row.get("Surprise(%)"))
        if reported is not None:
            surprises.append({
                "fiscal_date_ending": event_date.isoformat(),
                "reported_date": event_date.isoformat(),
                "reported_eps": reported,
                "estimated_eps": estimate,
                "surprise": reported - estimate if estimate is not None else None,
                "surprise_percentage": surprise_pct,
            })
        elif event_date >= today:
            calendar.append({
                "symbol": None,
                "name": None,
                "report_date": event_date.isoformat(),
                "fiscal_date_ending": None,
                "estimate": estimate,
                "currency": "USD",
                "time_of_day": None,
            })
    return surprises, calendar


class YahooEstimateProvider:
    def _ticker(self, ticker: str):
        policy_error = commercial_provider_error("yahoo_finance")
        if policy_error:
            return None, ProviderResult(status=ProviderStatus.ERROR, message=policy_error)
        return yf.Ticker(ticker), None

    def get_estimates(self, ticker: str) -> ProviderResult:
        obj, error = self._ticker(ticker)
        if error:
            return error
        try:
            rows = parse_yahoo_estimates(
                obj.get_earnings_estimate(), obj.get_revenue_estimate(),
            )
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        if not rows:
            return ProviderResult(status=ProviderStatus.ERROR, message=f"no Yahoo analyst estimates for {ticker}")
        return ProviderResult(status=ProviderStatus.OK, data={"rows": rows})

    def get_earnings_history(self, ticker: str) -> ProviderResult:
        obj, error = self._ticker(ticker)
        if error:
            return error
        try:
            surprises, _ = parse_yahoo_earnings_dates(obj.get_earnings_dates(limit=12))
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        if not surprises:
            return ProviderResult(status=ProviderStatus.ERROR, message=f"no Yahoo earnings history for {ticker}")
        return ProviderResult(status=ProviderStatus.OK, data={"rows": surprises})

    def get_earnings_calendar(self, ticker: str) -> ProviderResult:
        obj, error = self._ticker(ticker)
        if error:
            return error
        try:
            _, rows = parse_yahoo_earnings_dates(obj.get_earnings_dates(limit=12))
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        for row in rows:
            row["symbol"] = ticker.upper()
        if not rows:
            return ProviderResult(status=ProviderStatus.ERROR, message=f"no Yahoo earnings calendar for {ticker}")
        return ProviderResult(status=ProviderStatus.OK, data={"rows": rows})
