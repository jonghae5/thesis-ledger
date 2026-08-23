from datetime import date, datetime, timezone

import pytest

from src.models.enums import Decision
from src.models.schemas import (
    CatalystRow, CompanyRow, EstimateSnapshotRow, FundamentalSnapshotRow,
    GuidanceSnapshotRow, InvestmentAnalysisRow, MacroSnapshotRow, PriceRow, Provenance,
)
from src.storage import repository
from src.storage.db import get_connection, migrate


@pytest.fixture
def con(tmp_path):
    connection = get_connection(tmp_path / "test.duckdb")
    migrate(connection)
    yield connection
    connection.close()


def _prov(as_of=date(2026, 8, 21)):
    return Provenance(
        source="yahoo_finance", source_url="https://example.com",
        retrieved_at=datetime.now(timezone.utc), as_of_date=as_of,
    )


def test_macro_snapshots_are_append_only_and_support_as_of(con):
    for day, value in [(date(2026, 8, 20), 20.0), (date(2026, 8, 23), 28.0)]:
        timestamp = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
        repository.insert_macro_snapshots(con, [MacroSnapshotRow(
            indicator="VIX", snapshot_at=timestamp, observation_date=day,
            value=value, unit="index", source_type="FACT", transformation="LEVEL",
            source="fred", retrieved_at=timestamp,
        )])

    assert con.execute("SELECT COUNT(*) FROM macro_snapshots").fetchone()[0] == 2
    assert repository.get_latest_macro_snapshots(con)[0]["value"] == 28.0
    historical = repository.get_latest_macro_snapshots(con, as_of=date(2026, 8, 20))
    assert historical[0]["value"] == 20.0


def test_upsert_company_then_upsert_again_is_idempotent(con):
    repository.upsert_company(con, CompanyRow(ticker="NVDA", name="NVIDIA Corporation"))
    repository.upsert_company(con, CompanyRow(ticker="NVDA", name="NVIDIA Corp (updated)"))
    rows = con.execute("SELECT name FROM companies WHERE ticker = 'NVDA'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "NVIDIA Corp (updated)"


def test_upsert_prices_writes_and_updates_on_conflict(con):
    row = PriceRow(ticker="NVDA", date=date(2026, 8, 21), open=100, high=105, low=99, close=104, volume=1000, provenance=_prov())
    n = repository.upsert_prices(con, [row])
    assert n == 1
    updated = PriceRow(ticker="NVDA", date=date(2026, 8, 21), open=100, high=110, low=99, close=110, volume=2000, provenance=_prov())
    repository.upsert_prices(con, [updated])
    rows = con.execute("SELECT close, volume FROM prices WHERE ticker='NVDA' AND date=?", [date(2026, 8, 21)]).fetchall()
    assert len(rows) == 1
    assert rows[0] == (110.0, 2000)


def test_get_latest_prices_returns_rows_as_dicts(con):
    for d, close in [(date(2026, 8, 20), 100), (date(2026, 8, 21), 104)]:
        repository.upsert_prices(con, [PriceRow(ticker="NVDA", date=d, open=close, high=close, low=close, close=close, volume=1000, provenance=_prov(d))])
    rows = repository.get_latest_prices(con, "NVDA", limit=10)
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-08-21"  # most recent first


def test_estimate_snapshot_is_append_only(con):
    row = EstimateSnapshotRow(ticker="NVDA", snapshot_at=datetime(2026, 8, 15, tzinfo=timezone.utc), fiscal_period="FY2027", eps_mean=4.0, provenance=_prov())
    id1 = repository.insert_estimate_snapshot(con, row)
    row2 = EstimateSnapshotRow(ticker="NVDA", snapshot_at=datetime(2026, 8, 22, tzinfo=timezone.utc), fiscal_period="FY2027", eps_mean=4.2, provenance=_prov())
    id2 = repository.insert_estimate_snapshot(con, row2)
    assert id1 != id2
    count = con.execute("SELECT COUNT(*) FROM estimate_snapshots WHERE ticker='NVDA'").fetchone()[0]
    assert count == 2


def test_estimate_snapshot_query_isolates_fiscal_period(con):
    for period, eps in [("2027-01-31", 4.2), ("2028-01-31", 5.5)]:
        repository.insert_estimate_snapshot(con, EstimateSnapshotRow(
            ticker="NVDA", snapshot_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
            fiscal_period=period, eps_mean=eps, provenance=_prov(),
        ))
    rows = repository.get_estimate_snapshots(
        con, "NVDA", fiscal_period="2027-01-31",
    )
    assert len(rows) == 1
    assert rows[0]["eps_mean"] == 4.2


def test_annual_fundamentals_as_of_does_not_time_travel(con):
    old = FundamentalSnapshotRow(
        ticker="NVDA", period="2025-01-31", filed_at=date(2025, 2, 26),
        accession="0001-25-000001", form="10-K", fiscal_period="FY",
        revenue=100.0, provenance=_prov(date(2025, 2, 26)),
    )
    repository.upsert_fundamental_snapshots(con, [old])
    rows_before_filing = repository.get_annual_fundamentals_as_of(
        con, "NVDA", date(2025, 2, 25),
    )
    rows_after_filing = repository.get_annual_fundamentals_as_of(
        con, "NVDA", date(2025, 2, 26),
    )
    assert rows_before_filing == []
    assert rows_after_filing[0]["revenue"] == 100.0


def test_fundamental_quality_inputs_and_concepts_round_trip(con):
    row = FundamentalSnapshotRow(
        ticker="NVDA", period="2025-01-31", filed_at=date(2025, 2, 26),
        accession="0001-25-000001", form="10-K", fiscal_period="FY",
        revenue=100.0, assets=200.0, stockholders_equity=120.0,
        pretax_income=20.0, income_tax_expense=4.0, sbc=3.0,
        accounts_receivable=12.0, inventory=8.0, accounts_payable=10.0,
        source_concepts={
            "assets": "Assets",
            "sbc": "ShareBasedCompensation",
        },
        provenance=_prov(date(2025, 2, 26)),
    )

    repository.upsert_fundamental_snapshots(con, [row])

    annual = repository.get_annual_fundamentals_as_of(
        con, "NVDA", date(2025, 2, 26),
    )[0]
    snapshots = repository.get_fundamental_snapshots_as_of(
        con, "NVDA", date(2025, 2, 26),
    )[0]
    assert annual["assets"] == 200.0
    assert annual["sbc"] == 3.0
    assert annual["source_concepts"]["sbc"] == "ShareBasedCompensation"
    assert snapshots["accounts_receivable"] == 12.0
    assert snapshots["source_concepts"]["assets"] == "Assets"


def test_insert_guidance_snapshot_and_investment_analysis_and_catalyst(con):
    gid = repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
        ticker="NVDA", snapshot_at=datetime.now(timezone.utc), revenue_low=190000.0,
        revenue_high=200000.0, source_filing="10-Q", source_date=date(2026, 8, 1),
        retrieved_at=datetime.now(timezone.utc),
    ))
    assert isinstance(gid, int)

    aid = repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime.now(timezone.utc), price=180.0,
        decision=Decision.ACCUMULATE, confidence=0.72, expected_return=0.17,
        thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
    ))
    assert isinstance(aid, int)

    cid = repository.insert_catalyst(con, CatalystRow(
        ticker="NVDA", event_date=date(2026, 11, 20), event_type="earnings",
        description="Q3 FY27 earnings", importance="HIGH",
    ))
    assert isinstance(cid, int)


def test_get_latest_guidance_snapshot_returns_none_when_empty(con):
    assert repository.get_latest_guidance_snapshot(con, "NVDA") is None


def test_get_latest_guidance_snapshot_returns_most_recent(con):
    repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
        ticker="NVDA", snapshot_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        revenue_low=180000.0, revenue_high=190000.0, source_filing="10-Q",
        source_date=date(2026, 6, 30), retrieved_at=datetime.now(timezone.utc),
    ))
    repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
        ticker="NVDA", snapshot_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        revenue_low=190000.0, revenue_high=200000.0, source_filing="10-Q",
        source_date=date(2026, 7, 31), retrieved_at=datetime.now(timezone.utc),
    ))
    latest = repository.get_latest_guidance_snapshot(con, "NVDA")
    assert latest["revenue_low"] == 190000.0
    assert latest["revenue_high"] == 200000.0


def test_get_latest_guidance_snapshot_filters_comparison_key(con):
    for period, low in [("FY2027", 180000.0), ("FY2028", 220000.0)]:
        repository.insert_guidance_snapshot(con, GuidanceSnapshotRow(
            ticker="NVDA", snapshot_at=datetime.now(timezone.utc),
            revenue_low=low, revenue_high=low + 10000,
            fiscal_period=period, guidance_scope="FULL_YEAR",
            currency="USD", value_unit="MILLIONS", source_filing="10-Q",
            source_date=date(2026, 8, 1), retrieved_at=datetime.now(timezone.utc),
        ))
    latest = repository.get_latest_guidance_snapshot(
        con, "NVDA", "FY2027", "FULL_YEAR", "USD", "MILLIONS",
    )
    assert latest["fiscal_period"] == "FY2027"
    assert latest["revenue_low"] == 180000.0


def test_get_catalysts_returns_sorted_and_filters_since(con):
    repository.insert_catalyst(con, CatalystRow(
        ticker="NVDA", event_date=date(2026, 11, 20), event_type="earnings",
        description="Q3 FY27 earnings", importance="HIGH",
    ))
    repository.insert_catalyst(con, CatalystRow(
        ticker="NVDA", event_date=date(2026, 9, 5), event_type="product_launch",
        description="New GPU architecture reveal", importance="MED",
    ))
    all_rows = repository.get_catalysts(con, "NVDA")
    assert [r["event_type"] for r in all_rows] == ["product_launch", "earnings"]

    filtered = repository.get_catalysts(con, "NVDA", since=date(2026, 10, 1))
    assert [r["event_type"] for r in filtered] == ["earnings"]


def test_get_latest_investment_analysis_returns_none_when_empty(con):
    assert repository.get_latest_investment_analysis(con, "NVDA") is None


def test_get_latest_investment_analysis_returns_most_recent(con):
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc), price=170.0,
        decision=Decision.WATCH, confidence=0.5, expected_return=0.05,
        thesis_json='["old thesis"]', variant_perception_json="{}", invalidation_json="[]",
    ))
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 8, 20, tzinfo=timezone.utc), price=214.0,
        decision=Decision.ACCUMULATE, confidence=0.72, expected_return=0.17,
        thesis_json='["new thesis"]', variant_perception_json="{}", invalidation_json="[]",
    ))
    latest = repository.get_latest_investment_analysis(con, "NVDA")
    assert latest["decision"] == "ACCUMULATE"
    assert latest["thesis_json"] == '["new thesis"]'


def test_investment_analysis_persists_reproducibility_metadata(con):
    repository.insert_evidence_bundle(
        con, "bundle-1", "NVDA", datetime(2026, 8, 20, tzinfo=timezone.utc),
        "a" * 64, '{"ticker":"NVDA"}',
    )
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        price=214.0, decision=Decision.HOLD, confidence=0.6,
        expected_return=0.08, thesis_json="[]", variant_perception_json="{}",
        invalidation_json="[]", run_id="run-1", model_name="codex",
        model_version="gpt-5", prompt_version="investment-analysis-v1",
        input_snapshot_json='{"price_as_of":"2026-08-20"}',
        assumptions_json='["discount_rate=0.09"]',
        evidence_bundle_id="bundle-1",
    ))
    latest = repository.get_latest_investment_analysis(con, "NVDA")
    assert latest["run_id"] == "run-1"
    assert latest["input_snapshot_json"] == '{"price_as_of":"2026-08-20"}'
    assert latest["evidence_bundle_id"] == "bundle-1"
    assert repository.get_evidence_bundle(con, "bundle-1")["ticker"] == "NVDA"


def test_get_investment_analysis_history_orders_most_recent_first(con):
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc), price=170.0,
        decision=Decision.WATCH, confidence=0.5, expected_return=0.05,
        thesis_json='["old thesis"]', variant_perception_json="{}", invalidation_json="[]",
    ))
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 8, 20, tzinfo=timezone.utc), price=214.0,
        decision=Decision.ACCUMULATE, confidence=0.72, expected_return=0.17,
        thesis_json='["new thesis"]', variant_perception_json="{}", invalidation_json="[]",
    ))
    history = repository.get_investment_analysis_history(con, "NVDA")
    assert [h["decision"] for h in history] == ["ACCUMULATE", "WATCH"]
    assert history[0]["thesis_json"] == '["new thesis"]'


def test_get_investment_analysis_history_respects_limit(con):
    for i in range(5):
        repository.insert_investment_analysis(con, InvestmentAnalysisRow(
            ticker="NVDA", created_at=datetime(2026, 1, 1 + i, tzinfo=timezone.utc), price=100.0 + i,
            decision=Decision.HOLD, confidence=0.5, expected_return=0.05,
            thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
        ))
    history = repository.get_investment_analysis_history(con, "NVDA", limit=2)
    assert len(history) == 2


def test_get_investment_analysis_history_empty_returns_empty_list(con):
    assert repository.get_investment_analysis_history(con, "NVDA") == []
