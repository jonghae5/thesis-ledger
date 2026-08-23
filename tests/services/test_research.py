from datetime import date, datetime, timedelta, timezone

import pytest

from src.models.enums import Decision
from src.models.schemas import (
    CatalystRow,
    EstimateSnapshotRow,
    FundamentalSnapshotRow,
    GuidanceSnapshotRow,
    InvestmentAnalysisRow,
    MacroSnapshotRow,
    PriceRow,
    Provenance,
)
from src.services.research import build_evidence, compare_evidence, prepare_update
from src.storage import repository
from src.storage.db import get_connection, migrate


@pytest.fixture
def con(tmp_path):
    connection = get_connection(tmp_path / "research.duckdb")
    migrate(connection)
    yield connection
    connection.close()


def _provenance(as_of: date) -> Provenance:
    return Provenance(
        source="test", retrieved_at=datetime.now(timezone.utc), as_of_date=as_of,
    )


def _seed_company(con, ticker: str, price: float = 100.0) -> None:
    today = date.today()
    prices = []
    for days_ago in range(70, -1, -1):
        day = today - timedelta(days=days_ago)
        close = price * (1 + (70 - days_ago) / 1000)
        prices.append(PriceRow(
            ticker=ticker, date=day, open=close, high=close, low=close,
            close=close, volume=1000, provenance=_provenance(day),
        ))
    repository.upsert_prices(con, prices)

    for year_offset, revenue in [(2, 80.0), (1, 100.0)]:
        period = today - timedelta(days=365 * year_offset)
        filed_at = period + timedelta(days=45)
        repository.upsert_fundamental_snapshots(con, [FundamentalSnapshotRow(
            ticker=ticker, period=period.isoformat(), filed_at=filed_at,
            accession=f"{ticker}-{year_offset}", form="10-K", fiscal_period="FY",
            revenue=revenue, gross_profit=revenue * 0.7, net_income=revenue * 0.3,
            operating_cashflow=revenue * 0.4, capex=revenue * 0.05,
            fcf=revenue * 0.35, cash=10.0, debt=5.0, shares=10.0,
            currency="USD", provenance=_provenance(filed_at),
        )])

    fiscal_period = (today + timedelta(days=365)).isoformat()
    now = datetime.now(timezone.utc)
    for days_ago, eps in [(31, 4.0), (0, 4.2)]:
        snapshot_at = now - timedelta(days=days_ago)
        repository.insert_estimate_snapshot(con, EstimateSnapshotRow(
            ticker=ticker, snapshot_at=snapshot_at, fiscal_period=fiscal_period,
            eps_mean=eps, revenue_mean=120.0 + eps, analyst_count=20,
            provenance=_provenance(snapshot_at.date()),
        ))

    repository.insert_catalyst(con, CatalystRow(
        ticker=ticker, event_date=today + timedelta(days=30),
        event_type="earnings", description="Next earnings", importance="HIGH",
    ))
    repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
        ticker=ticker, snapshot_at=now, revenue_low=120.0, revenue_high=130.0,
        source_filing="10-Q", source_date=today,
        retrieved_at=now,
    ))


def _seed_macro(con) -> None:
    now = datetime.now(timezone.utc)
    indicators = {
        "FED_FUNDS": 4.5, "REAL_YIELD_10Y": 1.8, "YIELD_CURVE_10Y2Y": 0.2,
        "CORE_PCE_YOY": 2.7, "BREAKEVEN_INFLATION_10Y": 2.3,
        "UNEMPLOYMENT_RATE": 4.2, "INITIAL_CLAIMS": 230000, "SAHM_RULE": 0.2,
        "HY_OAS": 3.5, "NFCI": -0.2, "VIX": 18.0, "FEAR_GREED": 50.0,
    }
    repository.insert_macro_snapshots(con, [MacroSnapshotRow(
        indicator=indicator, snapshot_at=now, observation_date=date.today(), value=value,
        unit="index", source_type="FACT", transformation="LEVEL",
        reference_date=date.today() - timedelta(days=30), reference_value=value,
        source="test", retrieved_at=now,
    ) for indicator, value in indicators.items()])


def test_evidence_is_complete_when_decision_inputs_exist(con):
    _seed_company(con, "AAA")
    _seed_macro(con)

    evidence = build_evidence(con, "AAA")

    assert evidence["quality"]["quality"] == "COMPLETE"
    assert evidence["quality"]["can_analyze"] is True
    assert evidence["sections"]["market"]["status"] == "OK"
    assert evidence["sections"]["revisions"]["revision_score"] is not None
    assert evidence["sections"]["implied_expectations"]["implied_revenue_cagr"] is not None
    assert evidence["sections"]["macro"]["status"] == "OK"


def test_evidence_without_macro_is_partial_but_decision_remains_usable(con):
    _seed_company(con, "AAA")
    evidence = build_evidence(con, "AAA")
    assert evidence["quality"]["quality"] == "PARTIAL"
    assert evidence["quality"]["can_analyze"] is True
    assert "macro-sensitive scenario calibration" in evidence["quality"]["cannot_conclude"]


def test_evidence_refuses_to_analyze_without_core_inputs(con):
    evidence = build_evidence(con, "EMPTY")

    assert evidence["quality"]["quality"] == "INSUFFICIENT"
    assert evidence["quality"]["can_analyze"] is False
    assert {"market", "fundamentals", "valuation"}.issubset(evidence["quality"]["missing"])


def test_evidence_marks_old_consensus_stale(con):
    _seed_company(con, "AAA")
    con.execute(
        "UPDATE estimate_snapshots SET snapshot_at = ? WHERE ticker = 'AAA'",
        [datetime.now(timezone.utc) - timedelta(days=10)],
    )

    evidence = build_evidence(con, "AAA")

    assert evidence["sections"]["expectations"]["status"] == "STALE"
    assert evidence["quality"]["quality"] == "PARTIAL"
    assert evidence["quality"]["analysis_mode"] == "RESEARCH_ONLY"
    assert evidence["quality"]["can_research"] is True
    assert evidence["quality"]["can_decide"] is False
    assert evidence["quality"]["can_analyze"] is False
    assert "consensus gap" in evidence["quality"]["cannot_conclude"]


def test_compare_keeps_peer_metrics_separate_without_composite_score(con):
    _seed_company(con, "AAA", price=100.0)
    _seed_company(con, "BBB", price=150.0)

    comparison = compare_evidence([
        build_evidence(con, "AAA"), build_evidence(con, "BBB"),
    ])

    assert comparison["tickers"] == ["AAA", "BBB"]
    assert len(comparison["rows"]) == 2
    assert "score" not in comparison["rows"][0]
    assert comparison["rows"][1]["price"] > comparison["rows"][0]["price"]


def test_prepare_update_combines_previous_analysis_changes_and_evidence(con):
    _seed_company(con, "AAA")
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="AAA", created_at=datetime.now(timezone.utc) - timedelta(days=20),
        price=95.0, decision=Decision.HOLD, confidence=0.6,
        expected_return=0.1, thesis_json="[]", variant_perception_json="{}",
        invalidation_json="[]",
    ))

    prepared = prepare_update(con, "AAA")

    assert prepared["status"] == "READY"
    assert prepared["previous_analysis"]["decision"] == "HOLD"
    assert prepared["changes_since_previous"]["status"] == "OK"
    assert prepared["evidence"]["quality"]["can_analyze"] is True
