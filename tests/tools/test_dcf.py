import pytest

from src.tools.dcf import (
    faded_dcf_breakdown,
    faded_scenario_metrics,
    faded_target_price,
    implied_growth_rate,
    probability_weighted_value,
    project_enterprise_value,
    project_enterprise_value_fade,
)


def test_project_enterprise_value_is_monotonic_in_growth():
    low = project_enterprise_value(100.0, fcf_margin=0.3, growth=0.05, discount_rate=0.09, terminal_growth=0.025, years=10)
    high = project_enterprise_value(100.0, fcf_margin=0.3, growth=0.20, discount_rate=0.09, terminal_growth=0.025, years=10)
    assert high > low


def test_project_enterprise_value_raises_when_terminal_growth_exceeds_discount_rate():
    with pytest.raises(ValueError):
        project_enterprise_value(100.0, fcf_margin=0.3, growth=0.1, discount_rate=0.02, terminal_growth=0.03, years=10)


def test_implied_growth_rate_round_trips_through_project_enterprise_value():
    true_growth = 0.18
    target_ev = project_enterprise_value(100.0, fcf_margin=0.35, growth=true_growth, discount_rate=0.09, terminal_growth=0.025, years=10)
    solved = implied_growth_rate(100.0, fcf_margin=0.35, target_enterprise_value=target_ev, discount_rate=0.09, terminal_growth=0.025, years=10)
    assert solved == pytest.approx(true_growth, abs=1e-4)


def test_implied_growth_rate_raises_on_non_positive_margin():
    with pytest.raises(ValueError):
        implied_growth_rate(100.0, fcf_margin=0.0, target_enterprise_value=500.0)


def test_implied_growth_rate_rejects_target_outside_search_range():
    maximum_supported_ev = project_enterprise_value(
        100.0, fcf_margin=0.35, growth=5.0,
    )
    with pytest.raises(ValueError, match="outside the supported search range"):
        implied_growth_rate(
            100.0, fcf_margin=0.35,
            target_enterprise_value=maximum_supported_ev * 1.01,
        )


def test_probability_weighted_value_computes_expectation():
    scenarios = [
        {"probability": 0.25, "target_price": 100.0},
        {"probability": 0.50, "target_price": 150.0},
        {"probability": 0.25, "target_price": 210.0},
    ]
    value = probability_weighted_value(scenarios)
    assert value == pytest.approx(0.25 * 100.0 + 0.50 * 150.0 + 0.25 * 210.0)


def test_probability_weighted_value_raises_when_probabilities_dont_sum_to_one():
    with pytest.raises(ValueError):
        probability_weighted_value([{"probability": 0.5, "target_price": 100.0}, {"probability": 0.2, "target_price": 200.0}])


def test_probability_weighted_value_rejects_negative_probability_even_if_sum_is_one():
    with pytest.raises(ValueError, match="between 0 and 1"):
        probability_weighted_value([
            {"probability": -0.2, "target_price": 100.0},
            {"probability": 1.2, "target_price": 200.0},
        ])


def test_faded_dcf_is_sensitive_to_growth_margin_and_dilution():
    base = project_enterprise_value_fade(
        100.0, starting_margin=0.20, initial_growth=0.15, mature_margin=0.25,
    )
    stronger = project_enterprise_value_fade(
        100.0, starting_margin=0.20, initial_growth=0.20, mature_margin=0.30,
    )
    assert stronger > base > 0

    undiluted = faded_target_price(
        100.0, 0.20, 0.15, 0.25, shares=10.0, net_debt=0.0,
    )
    diluted = faded_target_price(
        100.0, 0.20, 0.15, 0.25, shares=10.0, net_debt=0.0,
        annual_dilution=0.02,
    )
    assert undiluted > diluted > 0


def test_faded_scenario_reports_terminal_value_and_return_diagnostics():
    breakdown = faded_dcf_breakdown(
        100.0, starting_margin=0.20, initial_growth=0.15, mature_margin=0.25,
    )
    assert breakdown["enterprise_value"] == pytest.approx(
        breakdown["explicit_period_pv"] + breakdown["terminal_value_pv"]
    )
    assert 0 < breakdown["terminal_value_pct"] < 1

    metrics = faded_scenario_metrics(
        100.0, 0.20, 0.15, 0.25, shares=10.0, net_debt=0.0,
        current_price=10.0, annual_dilution=0.01,
    )
    assert metrics["target_price"] > 0
    assert metrics["upside_downside"] == pytest.approx(metrics["target_price"] / 10.0 - 1)
    assert metrics["cumulative_dilution"] == pytest.approx(1.01 ** 10 - 1)


def test_faded_dcf_allows_negative_starting_margin_but_not_negative_mature_margin():
    breakdown = faded_dcf_breakdown(
        100.0, starting_margin=-0.10, initial_growth=0.10, mature_margin=0.15,
    )
    assert breakdown["enterprise_value"] > 0

    with pytest.raises(ValueError, match="mature_margin must be between 0 and 1"):
        faded_dcf_breakdown(
            100.0, starting_margin=0.10, initial_growth=0.10, mature_margin=-0.05,
        )
    with pytest.raises(ValueError, match="starting_margin must be between -1 and 1"):
        faded_dcf_breakdown(
            100.0, starting_margin=-1.5, initial_growth=0.10, mature_margin=0.15,
        )


def test_faded_dcf_uses_initial_growth_in_year_one_and_mature_margin_in_final_year():
    result = faded_dcf_breakdown(
        100.0, starting_margin=0.10, initial_growth=0.20,
        mature_margin=0.30, terminal_growth=0.02, years=2,
    )
    expected_final_revenue = 100.0 * 1.20 * 1.02
    assert result["final_year_revenue"] == pytest.approx(expected_final_revenue)
    assert result["final_year_fcf"] == pytest.approx(expected_final_revenue * 0.30)
