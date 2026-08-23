from datetime import date
from typing import List, Optional

import duckdb

from src.models.schemas import (
    CatalystRow, CompanyRow, EstimateSnapshotRow, FundamentalSnapshotRow,
    GuidanceSnapshotRow, InvestmentAnalysisRow, MacroSnapshotRow, PriceRow,
)


def upsert_company(con: duckdb.DuckDBPyConnection, row: CompanyRow) -> None:
    con.execute(
        """
        INSERT INTO companies (ticker, name, cik, sector, industry, exchange)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (ticker) DO UPDATE SET
            name = excluded.name, cik = excluded.cik, sector = excluded.sector,
            industry = excluded.industry, exchange = excluded.exchange
        """,
        [row.ticker, row.name, row.cik, row.sector, row.industry, row.exchange],
    )


def upsert_prices(con: duckdb.DuckDBPyConnection, rows: List[PriceRow]) -> int:
    for r in rows:
        con.execute(
            """
            INSERT INTO prices (ticker, date, open, high, low, close, volume, source, source_url, retrieved_at, as_of_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date) DO UPDATE SET
                open = excluded.open, high = excluded.high, low = excluded.low,
                close = excluded.close, volume = excluded.volume,
                source = excluded.source, source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at, as_of_date = excluded.as_of_date
            """,
            [r.ticker, r.date, r.open, r.high, r.low, r.close, r.volume,
             r.provenance.source, r.provenance.source_url, r.provenance.retrieved_at, r.provenance.as_of_date],
        )
    return len(rows)


def upsert_fundamental_snapshots(con: duckdb.DuckDBPyConnection, rows: List[FundamentalSnapshotRow]) -> int:
    for r in rows:
        con.execute(
            """
            INSERT INTO fundamental_snapshots (
                ticker, period, filed_at, accession, form, fiscal_year, fiscal_period,
                revenue, gross_profit, operating_income, net_income, operating_cashflow,
                capex, fcf, cash, debt, shares, currency, source, source_url, retrieved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, accession, period) DO UPDATE SET
                filed_at = excluded.filed_at, form = excluded.form,
                fiscal_year = excluded.fiscal_year, fiscal_period = excluded.fiscal_period,
                revenue = excluded.revenue, gross_profit = excluded.gross_profit,
                operating_income = excluded.operating_income, net_income = excluded.net_income,
                operating_cashflow = excluded.operating_cashflow, capex = excluded.capex,
                fcf = excluded.fcf, cash = excluded.cash, debt = excluded.debt,
                shares = excluded.shares, currency = excluded.currency,
                source = excluded.source, source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at
            """,
            [
                r.ticker, r.period, r.filed_at, r.accession, r.form,
                r.fiscal_year, r.fiscal_period, r.revenue, r.gross_profit,
                r.operating_income, r.net_income, r.operating_cashflow, r.capex,
                r.fcf, r.cash, r.debt, r.shares, r.currency,
                r.provenance.source, r.provenance.source_url, r.provenance.retrieved_at,
            ],
        )
    return len(rows)


def insert_estimate_snapshot(con: duckdb.DuckDBPyConnection, row: EstimateSnapshotRow) -> int:
    result = con.execute(
        """
        INSERT INTO estimate_snapshots
            (ticker, snapshot_at, fiscal_period, eps_mean, eps_high, eps_low,
             revenue_mean, revenue_high, revenue_low, analyst_count,
             eps_mean_7d_ago, eps_mean_30d_ago, eps_mean_90d_ago,
             revenue_mean_7d_ago, revenue_mean_30d_ago, revenue_mean_90d_ago,
             source, source_url, retrieved_at, as_of_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [row.ticker, row.snapshot_at, row.fiscal_period, row.eps_mean, row.eps_high, row.eps_low,
         row.revenue_mean, row.revenue_high, row.revenue_low, row.analyst_count,
         row.eps_mean_7d_ago, row.eps_mean_30d_ago, row.eps_mean_90d_ago,
         row.revenue_mean_7d_ago, row.revenue_mean_30d_ago, row.revenue_mean_90d_ago,
         row.provenance.source, row.provenance.source_url, row.provenance.retrieved_at, row.provenance.as_of_date],
    ).fetchone()
    return result[0]


def insert_macro_snapshots(con: duckdb.DuckDBPyConnection, rows: List[MacroSnapshotRow]) -> int:
    for row in rows:
        con.execute(
            """
            INSERT INTO macro_snapshots (
                indicator, snapshot_at, observation_date, value, unit, source_type,
                transformation, reference_date, reference_value, source, source_url,
                retrieved_at, percentile_5y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row.indicator, row.snapshot_at, row.observation_date, row.value,
                row.unit, row.source_type, row.transformation, row.reference_date,
                row.reference_value, row.source, row.source_url, row.retrieved_at,
                row.percentile_5y,
            ],
        )
    return len(rows)


def insert_guidance_snapshot(con: duckdb.DuckDBPyConnection, row: GuidanceSnapshotRow) -> int:
    result = con.execute(
        """
        INSERT INTO guidance_snapshots
            (ticker, snapshot_at, revenue_low, revenue_high, margin_guidance,
             capex_guidance, fiscal_period, guidance_scope, currency, value_unit,
             source_filing, source_date, retrieved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [row.ticker, row.snapshot_at, row.revenue_low, row.revenue_high, row.margin_guidance,
         row.capex_guidance, row.fiscal_period, row.guidance_scope, row.currency, row.value_unit,
         row.source_filing, row.source_date, row.retrieved_at],
    ).fetchone()
    return result[0]


def insert_investment_analysis(con: duckdb.DuckDBPyConnection, row: InvestmentAnalysisRow) -> int:
    result = con.execute(
        """
        INSERT INTO investment_analysis
            (ticker, created_at, price, decision, confidence, expected_return,
             expected_return_horizon_months, expected_return_method,
             expected_return_annualized, expected_return_basis,
             bull_value, base_value, bear_value,
             thesis_json, variant_perception_json, invalidation_json,
             run_id, model_name, model_version, prompt_version,
             input_snapshot_json, assumptions_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [row.ticker, row.created_at, row.price, row.decision.value, row.confidence, row.expected_return,
         row.expected_return_horizon_months, row.expected_return_method,
         row.expected_return_annualized, row.expected_return_basis,
         row.bull_value, row.base_value, row.bear_value,
         row.thesis_json, row.variant_perception_json, row.invalidation_json,
         row.run_id, row.model_name, row.model_version, row.prompt_version,
         row.input_snapshot_json, row.assumptions_json],
    ).fetchone()
    return result[0]


def insert_catalyst(con: duckdb.DuckDBPyConnection, row: CatalystRow) -> int:
    result = con.execute(
        """
        INSERT INTO catalysts (ticker, event_date, event_type, description, importance)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
        """,
        [row.ticker, row.event_date, row.event_type, row.description, row.importance],
    ).fetchone()
    return result[0]


def get_latest_prices(con: duckdb.DuckDBPyConnection, ticker: str, limit: int = 400) -> List[dict]:
    cols = [
        "ticker", "date", "open", "high", "low", "close", "volume",
        "source", "source_url", "retrieved_at", "as_of_date",
    ]
    result = con.execute(
        f"SELECT {', '.join(cols)} FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT ?",
        [ticker, limit],
    ).fetchall()
    rows = [dict(zip(cols, r)) for r in result]
    for r in rows:
        r["date"] = r["date"].isoformat()
        r["retrieved_at"] = r["retrieved_at"].isoformat()
        r["as_of_date"] = r["as_of_date"].isoformat()
    return rows


def get_latest_guidance_snapshot(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    fiscal_period: Optional[str] = None,
    guidance_scope: Optional[str] = None,
    currency: Optional[str] = None,
    value_unit: Optional[str] = None,
) -> Optional[dict]:
    cols = ["ticker", "snapshot_at", "revenue_low", "revenue_high", "margin_guidance",
            "capex_guidance", "fiscal_period", "guidance_scope", "currency", "value_unit",
            "source_filing", "source_date", "retrieved_at"]
    query = f"SELECT {', '.join(cols)} FROM guidance_snapshots WHERE ticker = ?"
    params = [ticker]
    for column, value in {
        "fiscal_period": fiscal_period,
        "guidance_scope": guidance_scope,
        "currency": currency,
        "value_unit": value_unit,
    }.items():
        if value is not None:
            query += f" AND {column} = ?"
            params.append(value)
    query += " ORDER BY snapshot_at DESC LIMIT 1"
    row = con.execute(query, params).fetchone()
    if row is None:
        return None
    result = dict(zip(cols, row))
    result["snapshot_at"] = result["snapshot_at"].isoformat()
    result["source_date"] = result["source_date"].isoformat()
    result["retrieved_at"] = result["retrieved_at"].isoformat()
    return result


def get_estimate_snapshots(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    limit: int = 50,
    fiscal_period: Optional[str] = None,
) -> List[dict]:
    cols = ["id", "ticker", "snapshot_at", "fiscal_period", "eps_mean", "eps_high", "eps_low",
            "revenue_mean", "revenue_high", "revenue_low", "analyst_count",
            "eps_mean_7d_ago", "eps_mean_30d_ago", "eps_mean_90d_ago",
            "revenue_mean_7d_ago", "revenue_mean_30d_ago", "revenue_mean_90d_ago",
            "source", "source_url", "retrieved_at", "as_of_date"]
    query = f"SELECT {', '.join(cols)} FROM estimate_snapshots WHERE ticker = ?"
    params: list = [ticker]
    if fiscal_period is not None:
        query += " AND fiscal_period = ?"
        params.append(fiscal_period)
    query += " ORDER BY snapshot_at DESC LIMIT ?"
    params.append(limit)
    result = con.execute(query, params).fetchall()
    rows = [dict(zip(cols, r)) for r in result]
    for r in rows:
        r["snapshot_at"] = r["snapshot_at"].isoformat()
        r["retrieved_at"] = r["retrieved_at"].isoformat()
        r["as_of_date"] = r["as_of_date"].isoformat()
    return rows


def get_latest_macro_snapshots(
    con: duckdb.DuckDBPyConnection,
    as_of: Optional[date] = None,
) -> List[dict]:
    cols = [
        "id", "indicator", "snapshot_at", "observation_date", "value", "unit",
        "source_type", "transformation", "reference_date", "reference_value",
        "source", "source_url", "retrieved_at", "percentile_5y",
    ]
    query = f"SELECT {', '.join(cols)} FROM macro_snapshots"
    params: list = []
    if as_of is not None:
        query += " WHERE CAST(snapshot_at AS DATE) <= ?"
        params.append(as_of)
    query += " QUALIFY ROW_NUMBER() OVER (PARTITION BY indicator ORDER BY snapshot_at DESC, id DESC) = 1"
    query += " ORDER BY indicator"
    rows = con.execute(query, params).fetchall()
    result = [dict(zip(cols, row)) for row in rows]
    for row in result:
        row["snapshot_at"] = row["snapshot_at"].isoformat()
        row["observation_date"] = row["observation_date"].isoformat()
        row["reference_date"] = row["reference_date"].isoformat() if row["reference_date"] else None
        row["retrieved_at"] = row["retrieved_at"].isoformat()
    return result


def get_fundamental_snapshots_as_of(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    as_of: date,
    limit: int = 400,
) -> List[dict]:
    """Return filing-time annual and discrete-quarter snapshots known by as_of."""
    cols = [
        "ticker", "period", "filed_at", "accession", "form",
        "fiscal_year", "fiscal_period", "revenue", "gross_profit",
        "operating_income", "net_income", "operating_cashflow", "capex",
        "fcf", "cash", "debt", "shares", "currency", "source",
        "source_url", "retrieved_at",
    ]
    rows = con.execute(
        f"""
        SELECT {', '.join(cols)}
        FROM fundamental_snapshots
        WHERE ticker = ?
          AND filed_at <= ?
          AND form IN ('10-K', '10-K/A', '10-Q', '10-Q/A')
        ORDER BY filed_at DESC, period DESC
        LIMIT ?
        """,
        [ticker, as_of, limit],
    ).fetchall()
    result = [dict(zip(cols, row)) for row in rows]
    for row in result:
        row["filed_at"] = row["filed_at"].isoformat()
        row["retrieved_at"] = row["retrieved_at"].isoformat()
    return result


def get_annual_fundamentals_as_of(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    as_of: date,
    limit: int = 8,
) -> List[dict]:
    """Return one latest-known annual filing snapshot per fiscal period."""
    cols = [
        "ticker", "period", "filed_at", "revenue", "gross_profit",
        "operating_income", "net_income", "operating_cashflow", "capex",
        "fcf", "cash", "debt", "shares", "currency", "accession", "form",
        "source", "source_url", "retrieved_at",
    ]
    rows = con.execute(
        f"""
        SELECT {', '.join(cols)}
        FROM fundamental_snapshots
        WHERE ticker = ?
          AND filed_at <= ?
          AND form IN ('10-K', '10-K/A')
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY period ORDER BY filed_at DESC, id DESC
        ) = 1
        ORDER BY period DESC
        LIMIT ?
        """,
        [ticker, as_of, limit],
    ).fetchall()
    result = [dict(zip(cols, r)) for r in rows]
    for r in result:
        r["reported_at"] = r.pop("filed_at").isoformat()
        r["retrieved_at"] = r["retrieved_at"].isoformat()
    return result


def get_catalysts(con: duckdb.DuckDBPyConnection, ticker: str, since: Optional[date] = None, limit: int = 50) -> List[dict]:
    cols = ["ticker", "event_date", "event_type", "description", "importance"]
    query = f"SELECT {', '.join(cols)} FROM catalysts WHERE ticker = ?"
    params: list = [ticker]
    if since is not None:
        query += " AND event_date >= ?"
        params.append(since)
    query += " ORDER BY event_date ASC LIMIT ?"
    params.append(limit)
    rows = con.execute(query, params).fetchall()
    result = [dict(zip(cols, r)) for r in rows]
    for r in result:
        r["event_date"] = r["event_date"].isoformat()
    return result


def get_latest_investment_analysis(con: duckdb.DuckDBPyConnection, ticker: str) -> Optional[dict]:
    cols = ["id", "ticker", "created_at", "price", "decision", "confidence", "expected_return",
            "expected_return_horizon_months", "expected_return_method",
            "expected_return_annualized", "expected_return_basis",
            "bull_value", "base_value", "bear_value",
            "thesis_json", "variant_perception_json", "invalidation_json",
            "run_id", "model_name", "model_version", "prompt_version",
            "input_snapshot_json", "assumptions_json"]
    row = con.execute(
        f"SELECT {', '.join(cols)} FROM investment_analysis WHERE ticker = ? ORDER BY created_at DESC LIMIT 1",
        [ticker],
    ).fetchone()
    if row is None:
        return None
    result = dict(zip(cols, row))
    result["created_at"] = result["created_at"].isoformat()
    return result


def get_investment_analysis_history(con: duckdb.DuckDBPyConnection, ticker: str, limit: int = 20) -> List[dict]:
    cols = ["id", "ticker", "created_at", "price", "decision", "confidence", "expected_return",
            "expected_return_horizon_months", "expected_return_method",
            "expected_return_annualized", "expected_return_basis",
            "bull_value", "base_value", "bear_value",
            "thesis_json", "variant_perception_json", "invalidation_json",
            "run_id", "model_name", "model_version", "prompt_version",
            "input_snapshot_json", "assumptions_json"]
    rows = con.execute(
        f"SELECT {', '.join(cols)} FROM investment_analysis WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
        [ticker, limit],
    ).fetchall()
    result = [dict(zip(cols, r)) for r in rows]
    for r in result:
        r["created_at"] = r["created_at"].isoformat()
    return result
