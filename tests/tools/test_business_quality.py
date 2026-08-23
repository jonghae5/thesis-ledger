import pytest

from src.tools.business_quality import compute_business_quality_inputs


def _annual_rows():
    return [
        {
            "ticker": "AAA", "period": "2023-12-31", "reported_at": "2024-02-15",
            "revenue": 100.0, "gross_profit": 40.0, "operating_income": 10.0,
            "net_income": 8.0, "operating_cashflow": 12.0, "capex": 5.0,
            "fcf": 7.0, "cash": 5.0, "debt": 20.0, "shares": 100.0,
            "assets": 200.0, "stockholders_equity": 100.0,
            "short_term_investments": 2.0, "current_debt": 5.0,
            "pretax_income": 8.0, "income_tax_expense": 2.0,
            "sbc": 3.0, "share_repurchases": 4.0,
            "accounts_receivable": 12.0, "inventory": 8.0,
            "accounts_payable": 10.0, "goodwill": 20.0,
            "acquisition_cash_paid": 5.0, "interest_expense": 2.0,
        },
        {
            "ticker": "AAA", "period": "2024-12-31", "reported_at": "2025-02-15",
            "revenue": 120.0, "gross_profit": 50.4, "operating_income": 15.0,
            "net_income": 12.0, "operating_cashflow": 18.0, "capex": 6.0,
            "fcf": 12.0, "cash": 8.0, "debt": 18.0, "shares": 102.0,
            "assets": 220.0, "stockholders_equity": 110.0,
            "short_term_investments": 2.0, "current_debt": 4.0,
            "pretax_income": 12.0, "income_tax_expense": 3.0,
            "sbc": 4.0, "share_repurchases": 6.0,
            "accounts_receivable": 14.0, "inventory": 9.0,
            "accounts_payable": 11.0, "goodwill": 22.0,
            "acquisition_cash_paid": 3.0, "interest_expense": 2.5,
        },
        {
            "ticker": "AAA", "period": "2025-12-31", "reported_at": "2026-02-15",
            "revenue": 150.0, "gross_profit": 66.0, "operating_income": 22.5,
            "net_income": 15.0, "operating_cashflow": 24.0, "capex": 7.5,
            "fcf": 16.5, "cash": 10.0, "debt": 15.0, "shares": 104.0,
            "assets": 250.0, "stockholders_equity": 130.0,
            "short_term_investments": 2.0, "current_debt": 3.0,
            "pretax_income": 18.0, "income_tax_expense": 4.5,
            "sbc": 5.0, "share_repurchases": 8.0,
            "accounts_receivable": 16.0, "inventory": 10.0,
            "accounts_payable": 12.0, "goodwill": 24.0,
            "acquisition_cash_paid": 2.0, "interest_expense": 3.0,
        },
    ]


def test_business_quality_inputs_are_score_free_and_separate_facts_from_models():
    result = compute_business_quality_inputs(_annual_rows())

    assert result["ticker"] == "AAA"
    assert result["source_type"] == "MODEL_OUTPUT"
    assert "score" not in result
    assert result["history"][0]["facts"]["source_type"] == "FACT"
    assert result["history"][0]["model_outputs"]["source_type"] == "MODEL_OUTPUT"
    assert result["history"][0]["facts"]["revenue"] == 100.0
    assert result["history"][0]["facts"]["debt"] == 20.0
    assert result["history"][0]["facts"]["current_debt"] == 5.0
    assert result["history"][0]["model_outputs"]["reported_debt"] == 25.0
    assert result["history"][0]["model_outputs"]["gross_margin"] == pytest.approx(0.4)
    assert result["profitability"]["gross_margin"]["latest"] == pytest.approx(0.44)
    assert result["profitability"]["gross_margin"]["observations"] == 3
    assert result["growth_and_reinvestment"]["revenue_cagr"]["value"] == pytest.approx(
        (150.0 / 100.0) ** 0.5 - 1, rel=1e-3,
    )
    assert result["growth_and_reinvestment"]["incremental_operating_margin"] == pytest.approx(0.25)
    assert result["cash_generation"]["cumulative_fcf_to_net_income"]["value"] == pytest.approx(
        35.5 / 35.0,
    )
    assert result["shareholder_and_balance_sheet"]["net_debt"]["latest"] == 8.0
    assert result["shareholder_and_balance_sheet"]["net_debt_to_fcf"]["latest"] == pytest.approx(
        8.0 / 16.5,
    )
    assert result["returns_on_capital"]["effective_tax_rate"]["latest"] == pytest.approx(0.25)
    assert result["returns_on_capital"]["roic"]["latest"] == pytest.approx(16.875 / 129.0)
    assert result["capital_allocation"]["sbc_to_revenue"]["latest"] == pytest.approx(
        5.0 / 150.0,
    )
    assert result["working_capital"]["working_capital_to_revenue"]["latest"] == pytest.approx(
        14.0 / 150.0,
    )
    assert result["ma_dependence"]["goodwill_to_assets"]["latest"] == pytest.approx(
        24.0 / 250.0,
    )
    assert result["ma_dependence"]["acquisition_cash_paid_to_revenue"][
        "latest"
    ] == pytest.approx(2.0 / 150.0)


def test_business_quality_inputs_preserve_missing_data_and_report_coverage_limits():
    row = {
        "ticker": "AAA", "period": "2025-12-31", "reported_at": "2026-02-15",
        "revenue": 100.0, "gross_profit": None, "operating_income": None,
        "net_income": -5.0, "operating_cashflow": 3.0, "capex": None,
        "fcf": None, "cash": None, "debt": None, "shares": None,
        "sbc": 2.0, "accounts_receivable": 10.0,
        "assets": 50.0, "goodwill": 5.0,
    }

    result = compute_business_quality_inputs([row])

    assert result["profitability"]["gross_margin"]["latest"] is None
    assert result["cash_generation"]["operating_cashflow_to_net_income"]["latest"] is None
    assert result["growth_and_reinvestment"]["revenue_cagr"]["value"] is None
    assert result["coverage"]["warnings"]
    assert len(result["coverage"]["unavailable_dimensions"]) == 2
    assert result["coverage"]["metric_availability"]["roic"] == "MISSING"
    assert result["coverage"]["metric_availability"]["sbc_to_revenue"] == "AVAILABLE"
    assert result["coverage"]["metric_availability"]["repurchases_to_sbc"] == "MISSING"
    assert result["coverage"]["metric_availability"]["receivables_to_revenue"] == "AVAILABLE"
    assert result["coverage"]["metric_availability"]["working_capital_to_revenue"] == "MISSING"
    assert result["coverage"]["metric_availability"]["goodwill_to_assets"] == "AVAILABLE"
    assert result["coverage"]["metric_availability"][
        "acquisition_cash_paid_to_revenue"
    ] == "MISSING"


def test_business_quality_inputs_raise_without_fundamentals():
    with pytest.raises(ValueError, match="no fundamentals rows"):
        compute_business_quality_inputs([])
