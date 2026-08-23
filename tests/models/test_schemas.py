from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.enums import Decision, ProviderStatus, SourceType
from src.models.schemas import (
    CatalystRow,
    CompanyRow,
    EstimateSnapshotRow,
    GuidanceSnapshotRow,
    InvestmentAnalysisRow,
    PriceRow,
    ProviderResult,
    Provenance,
)


def test_enums_have_expected_members():
    assert {e.value for e in SourceType} == {
        "FACT", "ESTIMATE", "MODEL_OUTPUT", "LLM_INFERENCE", "USER_ASSUMPTION",
    }
    assert {e.value for e in Decision} == {
        "STRONG_BUY", "ACCUMULATE", "HOLD", "WATCH", "REDUCE", "EXIT",
    }
    assert {e.value for e in ProviderStatus} == {"OK", "SKIPPED", "ERROR"}


def test_price_row_requires_provenance():
    prov = Provenance(
        source="yahoo_finance",
        source_url="https://finance.yahoo.com/quote/NVDA",
        retrieved_at=datetime.now(timezone.utc),
        as_of_date=date(2026, 8, 21),
    )
    row = PriceRow(
        ticker="NVDA", date=date(2026, 8, 21),
        open=100.0, high=105.0, low=99.0, close=104.0, volume=1000,
        provenance=prov,
    )
    assert row.ticker == "NVDA"
    assert row.provenance.source == "yahoo_finance"


def test_provider_result_skipped_has_no_data_requirement():
    result = ProviderResult(status=ProviderStatus.SKIPPED, message="no api key")
    assert result.data is None
    assert result.status == ProviderStatus.SKIPPED


def test_estimate_snapshot_row_and_guidance_row_and_investment_analysis_and_catalyst():
    prov = Provenance(
        source="alpha_vantage", source_url=None,
        retrieved_at=datetime.now(timezone.utc), as_of_date=date(2026, 8, 21),
    )
    EstimateSnapshotRow(
        ticker="NVDA", snapshot_at=datetime.now(timezone.utc), fiscal_period="FY2027",
        eps_mean=4.2, eps_high=4.5, eps_low=3.9, revenue_mean=200000.0,
        revenue_high=210000.0, revenue_low=190000.0, analyst_count=42,
        provenance=prov,
    )
    GuidanceSnapshotRow(
        ticker="NVDA", snapshot_at=datetime.now(timezone.utc),
        revenue_low=190000.0, revenue_high=200000.0, margin_guidance=0.75,
        capex_guidance=5000.0, source_filing="10-Q", source_date=date(2026, 8, 1),
        retrieved_at=datetime.now(timezone.utc),
    )
    InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime.now(timezone.utc), price=180.0,
        decision=Decision.ACCUMULATE, confidence=0.72, expected_return=0.17,
        thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
    )
    CatalystRow(
        ticker="NVDA", event_date=date(2026, 11, 20), event_type="earnings",
        description="Q3 FY27 earnings", importance="HIGH",
    )
    CompanyRow(ticker="NVDA", name="NVIDIA Corporation")


def test_holding_rejects_non_positive_position():
    with pytest.raises(ValidationError):
        from src.models.schemas import HoldingRow
        HoldingRow(ticker="NVDA", shares=-1, avg_cost=100, opened_at=date(2026, 1, 1))


def test_guidance_comparability_metadata_must_be_complete():
    with pytest.raises(ValidationError, match="comparability metadata"):
        GuidanceSnapshotRow(
            ticker="NVDA", snapshot_at=datetime.now(timezone.utc),
            revenue_low=190000, revenue_high=200000, fiscal_period="FY2027",
            source_filing="10-Q", source_date=date(2026, 8, 1),
            retrieved_at=datetime.now(timezone.utc),
        )


def test_investment_analysis_rejects_uncalibrated_confidence_range():
    with pytest.raises(ValidationError):
        InvestmentAnalysisRow(
            ticker="NVDA", created_at=datetime.now(timezone.utc), price=100,
            decision=Decision.HOLD, confidence=1.2, expected_return=0.1,
            thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
        )


def test_investment_analysis_rejects_inverted_scenarios():
    with pytest.raises(ValidationError, match="bear_value <= base_value <= bull_value"):
        InvestmentAnalysisRow(
            ticker="NVDA", created_at=datetime.now(timezone.utc), price=100,
            decision=Decision.HOLD, confidence=0.5, expected_return=0.1,
            bear_value=120, base_value=100, bull_value=110,
            thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
        )


def test_investment_analysis_validates_expected_return_metadata_as_a_unit():
    with pytest.raises(ValidationError, match="metadata must be provided together"):
        InvestmentAnalysisRow(
            ticker="NVDA", created_at=datetime.now(timezone.utc), price=100,
            decision=Decision.HOLD, confidence=0.5, expected_return=0.21,
            expected_return_horizon_months=24,
            thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
        )

    with pytest.raises(ValidationError, match="does not match"):
        InvestmentAnalysisRow(
            ticker="NVDA", created_at=datetime.now(timezone.utc), price=100,
            decision=Decision.HOLD, confidence=0.5, expected_return=0.21,
            expected_return_horizon_months=24,
            expected_return_method="BASE_CASE_TARGET",
            expected_return_annualized=0.21,
            expected_return_basis="PRICE_RETURN",
            thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
        )


def test_estimate_snapshot_rejects_inverted_range():
    with pytest.raises(ValidationError, match="low <= mean <= high"):
        EstimateSnapshotRow(
            ticker="NVDA", snapshot_at=datetime.now(timezone.utc),
            fiscal_period="2027-01-31", eps_low=5.0, eps_mean=4.0, eps_high=6.0,
            provenance=Provenance(
                source="alpha_vantage", retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 8, 23),
            ),
        )


def test_guidance_rejects_inverted_revenue_range():
    with pytest.raises(ValidationError, match="revenue_low <= revenue_high"):
        GuidanceSnapshotRow(
            ticker="NVDA", snapshot_at=datetime.now(timezone.utc),
            revenue_low=200, revenue_high=100, source_filing="10-Q",
            source_date=date(2026, 8, 1), retrieved_at=datetime.now(timezone.utc),
        )
