from statistics import pstdev
from typing import List, Optional

from src.models.enums import SourceType


def _pct_return(closes: List[float], lookback: int) -> Optional[float]:
    if len(closes) <= lookback:
        return None
    return closes[-1] / closes[-1 - lookback] - 1


def compute_market_metrics(ticker: str, price_rows: List[dict], spy_rows: Optional[List[dict]] = None) -> dict:
    if not price_rows:
        raise ValueError(f"no price rows for {ticker}")

    ordered = sorted(price_rows, key=lambda r: r["date"])
    closes = [r["close"] for r in ordered]

    momentum_1m = _pct_return(closes, 21)
    momentum_3m = _pct_return(closes, 63)
    momentum_6m = _pct_return(closes, 126)
    momentum_12m = _pct_return(closes, 252)

    def _daily_returns(window: int) -> List[float]:
        tail = closes[-(window + 1):]
        return [tail[i] / tail[i - 1] - 1 for i in range(1, len(tail))]

    returns_20d = _daily_returns(20)
    returns_60d = _daily_returns(60)
    volatility_20d = pstdev(returns_20d) * (252 ** 0.5) if len(returns_20d) > 1 else None
    volatility_60d = pstdev(returns_60d) * (252 ** 0.5) if len(returns_60d) > 1 else None

    window_52w = closes[-252:]
    high_52w = max(window_52w) if window_52w else None
    distance_52w_high = closes[-1] / high_52w - 1 if high_52w else None

    window_200 = closes[-200:]
    dma_200 = sum(window_200) / len(window_200) if window_200 else None
    distance_200dma = closes[-1] / dma_200 - 1 if dma_200 else None

    relative_strength_spy = None
    if spy_rows:
        spy_closes = [r["close"] for r in sorted(spy_rows, key=lambda r: r["date"])]
        spy_1m = _pct_return(spy_closes, 21)
        if momentum_1m is not None and spy_1m is not None:
            relative_strength_spy = momentum_1m - spy_1m

    return {
        "ticker": ticker,
        "price": closes[-1],
        "momentum_1m": momentum_1m,
        "momentum_3m": momentum_3m,
        "momentum_6m": momentum_6m,
        "momentum_12m": momentum_12m,
        "volatility_20d": volatility_20d,
        "volatility_60d": volatility_60d,
        "distance_52w_high": distance_52w_high,
        "distance_200dma": distance_200dma,
        "relative_strength_spy": relative_strength_spy,
        "source_type": SourceType.MODEL_OUTPUT.value,
    }
