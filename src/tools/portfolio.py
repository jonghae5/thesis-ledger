from math import sqrt
from statistics import mean, pstdev
from typing import Dict, List, Optional


def summarize_portfolio(holdings: List[dict], prices: Dict[str, float]) -> dict:
    if not holdings:
        raise ValueError("no holdings")

    positions = []
    total_value = 0.0
    total_cost = 0.0
    for h in holdings:
        ticker = h["ticker"]
        price = prices.get(ticker)
        if price is None:
            raise ValueError(f"no price for {ticker} - run 'data fetch {ticker}' first")

        market_value = h["shares"] * price
        cost_basis = h["shares"] * h["avg_cost"]
        positions.append({
            "ticker": ticker,
            "shares": h["shares"],
            "avg_cost": h["avg_cost"],
            "price": price,
            "sector": h.get("sector"),
            "market_value": market_value,
            "cost_basis": cost_basis,
            "unrealized_gain_pct": (price - h["avg_cost"]) / h["avg_cost"] if h["avg_cost"] else None,
        })
        total_value += market_value
        total_cost += cost_basis

    for p in positions:
        p["weight"] = p["market_value"] / total_value if total_value else None

    positions.sort(key=lambda p: p["weight"] or 0.0, reverse=True)

    sector_exposure: Dict[str, float] = {}
    for p in positions:
        sector = p["sector"] or "UNKNOWN"
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + (p["weight"] or 0.0)

    return {
        "positions": positions,
        "total_market_value": total_value,
        "total_cost_basis": total_cost,
        "total_unrealized_gain_pct": (total_value - total_cost) / total_cost if total_cost else None,
        "top_holding_ticker": positions[0]["ticker"],
        "top_holding_weight": positions[0]["weight"],
        "sector_exposure": sector_exposure,
    }


def _returns_by_date(rows: List[dict]) -> Dict[str, float]:
    ordered = sorted(rows, key=lambda r: r["date"])
    returns: Dict[str, float] = {}
    for previous, current in zip(ordered, ordered[1:]):
        if previous["close"] and current["close"] is not None:
            returns[current["date"]] = current["close"] / previous["close"] - 1
    return returns


def _correlation(left: List[float], right: List[float]) -> Optional[float]:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_std = pstdev(left)
    right_std = pstdev(right)
    if left_std == 0 or right_std == 0:
        return None
    covariance = mean((a - mean(left)) * (b - mean(right)) for a, b in zip(left, right))
    return covariance / (left_std * right_std)


def compute_portfolio_risk(
    positions: List[dict],
    price_history: Dict[str, List[dict]],
    benchmark_rows: Optional[List[dict]] = None,
    min_observations: int = 20,
) -> dict:
    if not positions:
        raise ValueError("no positions")
    returns = {ticker: _returns_by_date(rows) for ticker, rows in price_history.items()}
    tickers = [p["ticker"] for p in positions]
    if any(t not in returns for t in tickers):
        raise ValueError("price history missing for one or more positions")

    common_dates = sorted(set.intersection(*(set(returns[t]) for t in tickers)))
    weights = {p["ticker"]: p["weight"] for p in positions}
    concentration_hhi = sum(weight ** 2 for weight in weights.values())
    result = {
        "observation_count": len(common_dates),
        "concentration_hhi": concentration_hhi,
        "effective_number_of_positions": 1 / concentration_hhi if concentration_hhi else None,
        "annualized_volatility": None,
        "max_drawdown": None,
        "beta_spy": None,
        "correlations": {},
        "status": "INSUFFICIENT_HISTORY" if len(common_dates) < min_observations else "OK",
    }

    for i, left in enumerate(tickers):
        for right in tickers[i + 1:]:
            pair_dates = sorted(set(returns[left]) & set(returns[right]))
            corr = _correlation(
                [returns[left][d] for d in pair_dates],
                [returns[right][d] for d in pair_dates],
            )
            result["correlations"][f"{left}:{right}"] = corr

    if len(common_dates) < min_observations:
        return result

    portfolio_returns = [
        sum(weights[t] * returns[t][d] for t in tickers)
        for d in common_dates
    ]
    result["annualized_volatility"] = pstdev(portfolio_returns) * sqrt(252)
    wealth = peak = 1.0
    max_drawdown = 0.0
    for daily_return in portfolio_returns:
        wealth *= 1 + daily_return
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, wealth / peak - 1)
    result["max_drawdown"] = max_drawdown

    if benchmark_rows:
        benchmark = _returns_by_date(benchmark_rows)
        aligned_dates = [d for d in common_dates if d in benchmark]
        if len(aligned_dates) >= min_observations:
            portfolio_by_date = dict(zip(common_dates, portfolio_returns))
            p = [portfolio_by_date[d] for d in aligned_dates]
            b = [benchmark[d] for d in aligned_dates]
            benchmark_variance = pstdev(b) ** 2
            if benchmark_variance > 0:
                covariance = mean((x - mean(p)) * (y - mean(b)) for x, y in zip(p, b))
                result["beta_spy"] = covariance / benchmark_variance
    return result
