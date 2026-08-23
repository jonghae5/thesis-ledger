import json
from datetime import date, datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.models.enums import ProviderStatus
from src.models.schemas import EstimateSnapshotRow, FundamentalSnapshotRow, ProviderResult, Provenance
from src.storage import repository
from src.storage.db import get_connection, migrate

runner = CliRunner()


def _macro_provider_row(indicator="VIX", value=30.0):
    now = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    return {
        "indicator": indicator, "snapshot_at": now.isoformat(),
        "observation_date": "2026-08-22", "value": value, "unit": "index",
        "source_type": "FACT", "transformation": "LEVEL",
        "reference_date": "2026-07-22", "reference_value": 20.0,
        "source": "test", "source_url": None, "retrieved_at": now.isoformat(),
    }


def test_macro_fetch_preserves_partial_provider_success(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setattr(
        "src.providers.macro.FredMacroProvider.get_snapshot",
        lambda self: ProviderResult(status=ProviderStatus.OK, data={"rows": [_macro_provider_row()]}),
    )
    monkeypatch.setattr(
        "src.providers.macro.FearGreedProvider.get_snapshot",
        lambda self: ProviderResult(status=ProviderStatus.ERROR, message="unavailable"),
    )

    result = runner.invoke(app, ["data", "macro-fetch"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PARTIAL"
    assert payload["saved"] == 1


def test_macro_command_reads_stored_context(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setattr(
        "src.providers.macro.FredMacroProvider.get_snapshot",
        lambda self: ProviderResult(status=ProviderStatus.OK, data={"rows": [_macro_provider_row()]}),
    )
    monkeypatch.setattr(
        "src.providers.macro.FearGreedProvider.get_snapshot",
        lambda self: ProviderResult(status=ProviderStatus.ERROR, message="unavailable"),
    )
    assert runner.invoke(app, ["data", "macro-fetch"]).exit_code == 0

    result = runner.invoke(app, ["data", "macro"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["groups"]["sentiment_stress"]["VIX"]["state"] == "EXTREME_STRESS"


def test_root_help_exposes_only_three_domains_and_doctor():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("data", "valuation", "analysis", "doctor"):
        assert command in result.stdout
    for legacy_command in ("seed-watchlist", "save-analysis", "add-holding", "portfolio"):
        assert legacy_command not in result.stdout


def test_seed_watchlist_inserts_five_companies(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    result = runner.invoke(app, ["data", "seed"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["seeded"]) == {"NVDA", "AAPL", "AMD", "META", "GOOGL"}

    con = get_connection(db_path)
    count = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    assert count == 5


def test_fetch_writes_prices_and_point_in_time_fundamentals(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    price_rows = [{
        "ticker": "NVDA", "date": "2026-08-21", "open": 100, "high": 105, "low": 99,
        "close": 104, "volume": 1000, "source": "yahoo_finance", "source_url": "https://x",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "as_of_date": "2026-08-21",
    }]
    monkeypatch.setattr(
        "src.providers.yahoo.YahooPriceProvider.get_prices",
        lambda self, ticker, period_days=400: ProviderResult(status=ProviderStatus.OK, data={"rows": price_rows}),
    )
    monkeypatch.setattr(
        "src.providers.sec.SecFilingProvider.get_company_facts",
        lambda self, ticker: ProviderResult(status=ProviderStatus.OK, data={"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [{
                "start": "2025-02-01", "end": "2026-01-31", "filed": "2026-02-25",
                "accn": "0001-26-000001", "val": 100.0, "form": "10-K", "fp": "FY", "fy": 2026,
            }]}}
        }}}),
    )

    result = runner.invoke(app, ["data", "fetch", "nvda"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ticker"] == "NVDA"
    assert payload["prices"]["status"] == "OK"
    assert payload["prices"]["rows_written"] == 1
    assert payload["fundamentals"]["rows_written"] == 1
    assert "estimates" not in payload

    con = get_connection(db_path)
    price_count = con.execute("SELECT COUNT(*) FROM prices WHERE ticker='NVDA'").fetchone()[0]
    snapshot_count = con.execute("SELECT COUNT(*) FROM fundamental_snapshots WHERE ticker='NVDA'").fetchone()[0]
    assert price_count == 1
    assert snapshot_count == 1


def test_fetch_fails_when_sec_response_has_no_supported_filing_facts(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    price_rows = [{
        "ticker": "NVDA", "date": "2026-08-21", "open": 100, "high": 105, "low": 99,
        "close": 104, "volume": 1000, "source": "yahoo_finance", "source_url": "https://x",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "as_of_date": "2026-08-21",
    }]
    monkeypatch.setattr(
        "src.providers.yahoo.YahooPriceProvider.get_prices",
        lambda self, ticker, period_days=400: ProviderResult(
            status=ProviderStatus.OK, data={"rows": price_rows},
        ),
    )
    monkeypatch.setattr(
        "src.providers.sec.SecFilingProvider.get_company_facts",
        lambda self, ticker: ProviderResult(
            status=ProviderStatus.OK, data={"facts": {"us-gaap": {}}},
        ),
    )

    result = runner.invoke(app, ["data", "fetch", "NVDA"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["prices"] == {"status": "OK", "rows_written": 1}
    assert payload["fundamentals"]["status"] == "ERROR"
    assert "no supported" in payload["fundamentals"]["message"]


def test_guidance_sources_command_returns_candidates_without_saving(monkeypatch):
    provider_data = {
        "ticker": "NVDA",
        "classification": "CANDIDATE_SOURCE",
        "filings": [{
            "filing_date": "2026-08-20",
            "filing_index_url": "https://www.sec.gov/example/index.html",
            "primary_document_url": "https://www.sec.gov/example/8-k.htm",
        }],
        "warning": "documents are candidate primary sources",
    }
    monkeypatch.setattr(
        "src.providers.sec.SecFilingProvider.get_guidance_sources",
        lambda self, ticker, lookback_days=365, limit=8: ProviderResult(
            status=ProviderStatus.OK, data=provider_data,
        ),
    )

    result = runner.invoke(app, [
        "data", "guidance-sources", "nvda", "--days", "180", "--limit", "4",
    ])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert payload["classification"] == "CANDIDATE_SOURCE"
    assert payload["filings"][0]["filing_index_url"].endswith("index.html")


def test_market_command_computes_metrics_from_stored_prices(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    for i in range(25):
        con.execute(
            "INSERT INTO prices VALUES (?, ?, 100, 100, 100, ?, 1000, 'yahoo_finance', NULL, ?, ?)",
            ["NVDA", date(2026, 7, 1 + i), 100 + i, datetime.now(timezone.utc), date(2026, 7, 1 + i)],
        )
    con.close()

    result = runner.invoke(app, ["data", "market", "NVDA", "--max-price-age-days", "60"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ticker"] == "NVDA"
    assert payload["price"] == 124


def test_market_command_rejects_stale_price_by_default(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    con.execute(
        "INSERT INTO prices VALUES (?, ?, 100, 100, 100, 100, 1000, 'yahoo_finance', NULL, ?, ?)",
        ["NVDA", date(2020, 1, 2), datetime.now(timezone.utc), date(2020, 1, 2)],
    )
    con.close()

    result = runner.invoke(app, ["data", "market", "NVDA"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_quality_command_returns_point_in_time_score_free_inputs(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    for period, filed_at, revenue, operating_income, shares in [
        ("2024-12-31", date(2025, 2, 15), 100.0, 10.0, 100.0),
        ("2025-12-31", date(2026, 2, 15), 120.0, 15.0, 102.0),
    ]:
        repository.upsert_fundamental_snapshots(con, [FundamentalSnapshotRow(
            ticker="AAA", period=period, filed_at=filed_at,
            accession=f"AAA-{period}", form="10-K", fiscal_period="FY",
            revenue=revenue, gross_profit=revenue * 0.4,
            operating_income=operating_income, net_income=operating_income * 0.8,
            operating_cashflow=operating_income, capex=revenue * 0.05,
            fcf=operating_income - revenue * 0.05, cash=5.0, debt=10.0,
            shares=shares, currency="USD",
            provenance=Provenance(
                source="sec_edgar", retrieved_at=datetime.now(timezone.utc),
                as_of_date=filed_at,
            ),
        )])
    con.close()

    result = runner.invoke(app, ["data", "quality", "aaa", "--as-of", "2026-03-01"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ticker"] == "AAA"
    assert payload["as_of_date"] == "2026-03-01"
    assert payload["coverage"]["annual_periods"] == 2
    assert payload["profitability"]["operating_margin"]["latest"] == pytest.approx(0.125)
    assert payload["source_type"] == "MODEL_OUTPUT"
    assert "score" not in payload


def test_expectations_command_writes_snapshot_and_returns_consensus(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    payload = {
        "symbol": "NVDA",
        "estimates": [
            {"date": "2028-01-31", "horizon": "fiscal year",
             "eps_estimate_average": "5.10", "eps_estimate_high": "5.40", "eps_estimate_low": "4.80",
             "eps_estimate_analyst_count": "45",
             "revenue_estimate_average": "220000000000", "revenue_estimate_high": "230000000000",
             "revenue_estimate_low": "210000000000", "revenue_estimate_analyst_count": "42"},
            {"date": "2027-01-31", "horizon": "fiscal year",
             "eps_estimate_average": "4.20", "eps_estimate_high": "4.50", "eps_estimate_low": "3.90",
             "eps_estimate_analyst_count": "48",
             "revenue_estimate_average": "165000000000", "revenue_estimate_high": "170000000000",
             "revenue_estimate_low": "160000000000", "revenue_estimate_analyst_count": "45"},
        ],
    }
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.OK, data=payload),
    )

    result = runner.invoke(app, ["data", "expectations", "nvda"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["ticker"] == "NVDA"
    assert out["eps"]["mean"] == 4.20
    assert out["revenue"]["mean"] == 165000000000.0

    con = get_connection(db_path)
    count = con.execute("SELECT COUNT(*) FROM estimate_snapshots WHERE ticker='NVDA'").fetchone()[0]
    assert count == 1


def test_expectations_command_reports_skipped_without_key(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.SKIPPED, message="ALPHA_VANTAGE_API_KEY not set"),
    )
    monkeypatch.setattr(
        "src.providers.yahoo.YahooEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.ERROR, message="unavailable"),
    )

    result = runner.invoke(app, ["data", "expectations", "NVDA"])
    assert result.exit_code == 1
    out = json.loads(result.stdout)
    assert out["status"] == "ERROR"
    assert len(out["provider_attempts"]) == 2


def test_expectations_command_falls_back_to_yahoo(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    repository.upsert_fundamental_snapshots(con, [FundamentalSnapshotRow(
        ticker="NVDA", period="2026-01-31", filed_at=date(2026, 2, 25),
        accession="fallback-1", form="10-K", fiscal_period="FY", revenue=100.0,
        provenance=Provenance(
            source="sec_edgar", retrieved_at=datetime.now(timezone.utc),
            as_of_date=date(2026, 2, 25),
        ),
    )])
    con.close()
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.ERROR, message="rate limit exceeded"),
    )
    monkeypatch.setattr(
        "src.providers.yahoo.YahooEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.OK, data={"rows": [{
            "period": "0y", "eps_mean": 5.0, "eps_high": 5.5, "eps_low": 4.5,
            "eps_analyst_count": 40, "revenue_mean": 200.0,
            "revenue_high": 220.0, "revenue_low": 180.0,
            "revenue_analyst_count": 38,
        }]}),
    )

    result = runner.invoke(app, ["data", "expectations", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["provider"] == "yahoo_finance"
    assert out["fallback_used"] is True
    con = get_connection(db_path)
    stored = repository.get_estimate_snapshots(con, "NVDA", limit=1)[0]
    assert stored["source"] == "yahoo_finance"


def test_expectations_command_returns_stale_snapshot_when_all_providers_fail(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    old = datetime.now(timezone.utc) - timedelta(days=5)
    repository.insert_estimate_snapshot(con, EstimateSnapshotRow(
        ticker="NVDA", snapshot_at=old, fiscal_period="2027-01-31",
        eps_mean=4.2, revenue_mean=165.0, analyst_count=40,
        provenance=Provenance(source="alpha_vantage", retrieved_at=old, as_of_date=old.date()),
    ))
    con.close()
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.ERROR, message="rate limit exceeded"),
    )
    monkeypatch.setattr(
        "src.providers.yahoo.YahooEstimateProvider.get_estimates",
        lambda self, ticker: ProviderResult(status=ProviderStatus.ERROR, message="unavailable"),
    )

    result = runner.invoke(app, ["data", "expectations", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["status"] == "STALE"
    assert out["saved"] is False
    assert out["eps"]["mean"] == 4.2


def test_revisions_command_computes_from_stored_snapshots(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    for days_ago, eps in [(31, 4.00), (0, 4.20)]:
        repository.insert_estimate_snapshot(con, EstimateSnapshotRow(
            ticker="NVDA",
            snapshot_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
            fiscal_period="2026-01-31", eps_mean=eps, revenue_mean=165000000000.0, analyst_count=45,
            provenance=Provenance(source="alpha_vantage", retrieved_at=datetime.now(timezone.utc), as_of_date=date(2026, 8, 21)),
        ))
    con.close()

    result = runner.invoke(app, ["data", "revisions", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["eps_revision_30d"] == pytest.approx((4.20 - 4.00) / 4.00)


def test_save_guidance_command_reports_first_snapshot_then_raised(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    first = runner.invoke(app, [
        "analysis", "save-guidance", "NVDA", "--revenue-low", "180000", "--revenue-high", "190000",
        "--fiscal-period", "FY2027", "--guidance-scope", "FULL_YEAR",
        "--currency", "USD", "--value-unit", "MILLIONS",
        "--source-filing", "10-Q", "--source-date", "2026-06-30",
    ])
    assert first.exit_code == 0
    assert json.loads(first.stdout)["trend"] == "FIRST_SNAPSHOT"

    second = runner.invoke(app, [
        "analysis", "save-guidance", "NVDA", "--revenue-low", "200000", "--revenue-high", "210000",
        "--fiscal-period", "FY2027", "--guidance-scope", "FULL_YEAR",
        "--currency", "USD", "--value-unit", "MILLIONS",
        "--source-filing", "10-Q", "--source-date", "2026-08-01",
    ])
    assert second.exit_code == 0
    assert json.loads(second.stdout)["trend"] == "RAISED"


def test_save_guidance_does_not_compare_different_fiscal_periods(tmp_path, monkeypatch):
    monkeypatch.setattr("src.cli.common.DB_PATH", tmp_path / "test.duckdb")
    common = [
        "--guidance-scope", "FULL_YEAR", "--currency", "USD", "--value-unit", "MILLIONS",
        "--source-filing", "10-Q",
    ]
    first = runner.invoke(app, [
        "analysis", "save-guidance", "NVDA", "--revenue-low", "180", "--revenue-high", "190",
        "--fiscal-period", "FY2027", "--source-date", "2026-06-30", *common,
    ])
    assert first.exit_code == 0
    second = runner.invoke(app, [
        "analysis", "save-guidance", "NVDA", "--revenue-low", "220", "--revenue-high", "230",
        "--fiscal-period", "FY2028", "--source-date", "2026-08-01", *common,
    ])
    assert second.exit_code == 0
    out = json.loads(second.stdout)
    assert out["trend"] == "NOT_COMPARABLE"
    assert out["latest_other_basis"]["fiscal_period"] == "FY2027"


def _seed_valuation_fixture(con, ticker="NVDA", price=200.0):
    price_date = date.today()
    con.execute(
        "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, 1000, 'yahoo_finance', NULL, ?, ?)",
        [ticker, price_date, price, price, price, price, datetime.now(timezone.utc), price_date],
    )
    repository.upsert_fundamental_snapshots(con, [FundamentalSnapshotRow(
        ticker=ticker, period="2026-01-25", filed_at=date(2026, 2, 25),
        accession=f"{ticker}-0001-26-000001", form="10-K", fiscal_year=2026, fiscal_period="FY",
        revenue=215938000000.0, gross_profit=153463000000.0,
        operating_income=100000000000.0, net_income=90000000000.0,
        operating_cashflow=102718000000.0, capex=7718000000.0,
        fcf=95000000000.0, cash=7469000000.0, debt=8463000000.0,
        shares=24304000000.0, currency="USD",
        provenance=Provenance(
            source="sec_edgar", retrieved_at=datetime.now(timezone.utc),
            as_of_date=date(2026, 2, 25),
        ),
    )])


def test_valuation_command_computes_multiples_from_stored_data(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con)
    con.close()

    result = runner.invoke(app, ["valuation", "multiples", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["ticker"] == "NVDA"
    assert out["trailing_pe"] is not None
    assert out["forward_pe"] is None  # no estimate_snapshots seeded


def test_reverse_dcf_command_returns_implied_growth(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con)
    con.close()

    result = runner.invoke(app, ["valuation", "reverse-dcf", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["ticker"] == "NVDA"
    assert isinstance(out["implied_revenue_cagr"], float)
    assert out["fcf_margin_assumed"] == pytest.approx(95000000000.0 / 215938000000.0)


def test_scenario_command_computes_weighted_value(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con)
    con.close()

    result = runner.invoke(app, [
        "valuation", "scenario", "NVDA",
        "--bear-growth", "0.10", "--bear-margin", "0.35", "--bear-prob", "0.25",
        "--base-growth", "0.20", "--base-margin", "0.40", "--base-prob", "0.50",
        "--bull-growth", "0.30", "--bull-margin", "0.45", "--bull-prob", "0.25",
        "--annual-dilution", "0.01",
    ])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["model"] == "FADED_DCF"
    assert out["bear"]["probability"] == 0.25
    assert out["bull"]["target_price"] > out["base"]["target_price"] > out["bear"]["target_price"]
    assert out["probability_weighted_value"] == pytest.approx(
        0.25 * out["bear"]["target_price"] + 0.50 * out["base"]["target_price"] + 0.25 * out["bull"]["target_price"]
    )
    assert out["base"]["initial_revenue_growth"] == 0.20
    assert out["base"]["mature_fcf_margin"] == 0.40
    assert 0 < out["base"]["terminal_value_pct"] < 1
    assert out["base"]["cumulative_dilution"] == pytest.approx(1.01 ** 10 - 1)
    assert out["base"]["final_year_revenue"] > 215938000000.0


def test_sensitivity_command_returns_three_by_three_matrix(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con)
    con.close()

    result = runner.invoke(app, [
        "valuation", "sensitivity", "NVDA",
        "--growth", "0.20", "--mature-margin", "0.35",
        "--annual-dilution", "0.01",
    ])

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["financial_basis"] == "ANNUAL_FALLBACK"
    assert len(out["discount_rates"]) == 3
    assert len(out["matrix"]) == 3
    assert all(len(row["values_by_discount_rate"]) == 3 for row in out["matrix"])


def test_evidence_command_returns_research_only_package_without_consensus(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con)
    con.close()

    result = runner.invoke(app, ["data", "evidence", "NVDA"])

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["quality"]["completeness"] == "PARTIAL"
    assert out["quality"]["can_research"] is True
    assert out["quality"]["can_decide"] is False
    assert "consensus gap" in out["quality"]["cannot_conclude"]


def test_evidence_command_exits_nonzero_when_core_inputs_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.cli.common.DB_PATH", tmp_path / "test.duckdb")

    result = runner.invoke(app, ["data", "evidence", "EMPTY"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["quality"]["completeness"] == "INSUFFICIENT"


def test_compare_command_returns_peer_rows_without_composite_score(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con, "AAA", 100.0)
    _seed_valuation_fixture(con, "BBB", 150.0)
    con.close()

    result = runner.invoke(app, ["data", "compare", "AAA", "BBB"])

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["tickers"] == ["AAA", "BBB"]
    assert "score" not in out["rows"][0]


def test_compare_command_exits_nonzero_when_no_peer_is_analyzable(tmp_path, monkeypatch):
    monkeypatch.setattr("src.cli.common.DB_PATH", tmp_path / "test.duckdb")

    result = runner.invoke(app, ["data", "compare", "AAA", "BBB"])

    assert result.exit_code == 1
    out = json.loads(result.stdout)
    assert out["can_research"] is False
    assert "insufficient evidence for: AAA, BBB" in out["warnings"]


def test_prepare_command_returns_evidence_and_no_history_state(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    _seed_valuation_fixture(con)
    con.close()

    result = runner.invoke(app, ["analysis", "prepare", "NVDA"])

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["previous_analysis"] is None
    assert out["evidence"]["quality"]["can_research"] is True
    assert out["evidence"]["quality"]["can_decide"] is False


from src.models.enums import Decision
from src.models.schemas import CatalystRow, InvestmentAnalysisRow


def test_earnings_surprise_falls_back_to_finnhub(monkeypatch):
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_earnings_history",
        lambda self, ticker: ProviderResult(status=ProviderStatus.ERROR, message="quota"),
    )
    monkeypatch.setattr(
        "src.providers.finnhub.FinnhubEarningsProvider.get_earnings_history",
        lambda self, ticker: ProviderResult(status=ProviderStatus.OK, data={"rows": [{
            "fiscal_date_ending": "2026-06-30", "reported_eps": 1.1,
            "estimated_eps": 1.0, "surprise": 0.1, "surprise_percentage": 10.0,
        }]}),
    )
    result = runner.invoke(app, ["data", "earnings-surprise", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["provider"] == "finnhub"
    assert out["fallback_used"] is True
    assert out["latest_surprise"] == 0.1


def test_news_command_returns_articles_with_key(monkeypatch):
    monkeypatch.setattr(
        "src.providers.finnhub.FinnhubNewsProvider.get_news",
        lambda self, ticker, days=7: ProviderResult(
            status=ProviderStatus.OK,
            data={"rows": [{"headline": "NVIDIA beats estimates", "source": "Reuters"}]},
        ),
    )

    result = runner.invoke(app, ["data", "news", "nvda", "--limit", "1"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ticker"] == "NVDA"
    assert payload["limit"] == 1
    assert payload["returned"] == 1
    assert payload["news"][0]["headline"] == "NVIDIA beats estimates"


def test_news_command_fails_without_key(monkeypatch):
    monkeypatch.setattr(
        "src.providers.finnhub.FinnhubNewsProvider.get_news",
        lambda self, ticker, days=7: ProviderResult(status=ProviderStatus.SKIPPED, message="FINNHUB_API_KEY not set"),
    )

    result = runner.invoke(app, ["data", "news", "NVDA"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "SKIPPED"


def test_save_catalyst_command_inserts_row(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    result = runner.invoke(app, [
        "analysis", "save-catalyst", "NVDA", "--event-date", "2026-09-05",
        "--event-type", "product_launch", "--description", "New GPU architecture reveal",
        "--importance", "MED",
    ])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["ticker"] == "NVDA"
    assert out["saved"] is True

    con = get_connection(db_path)
    count = con.execute("SELECT COUNT(*) FROM catalysts WHERE ticker='NVDA'").fetchone()[0]
    assert count == 1


def test_catalysts_command_merges_stored_and_calendar(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    repository.insert_catalyst(con, CatalystRow(
        ticker="NVDA", event_date=date(2026, 9, 5), event_type="product_launch",
        description="GPU reveal", importance="MED",
    ))
    con.close()

    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_earnings_calendar",
        lambda self, ticker, horizon="12month": ProviderResult(status=ProviderStatus.OK, data={"rows": [
            {"symbol": "NVDA", "name": "NVIDIA Corp", "report_date": "2026-11-19",
             "fiscal_date_ending": "2026-10-31", "estimate": 1.28, "currency": "USD", "time_of_day": "post-market"},
        ]}),
    )

    result = runner.invoke(app, ["data", "catalysts", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert [c["event_type"] for c in out["catalysts"]] == ["product_launch", "earnings"]


def test_catalysts_command_works_without_av_key(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    repository.insert_catalyst(con, CatalystRow(
        ticker="NVDA", event_date=date(2026, 9, 5), event_type="product_launch",
        description="GPU reveal", importance="MED",
    ))
    con.close()
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_earnings_calendar",
        lambda self, ticker, horizon="12month": ProviderResult(status=ProviderStatus.SKIPPED, message="ALPHA_VANTAGE_API_KEY not set"),
    )
    monkeypatch.setattr(
        "src.providers.finnhub.FinnhubEarningsProvider.get_earnings_calendar",
        lambda self, ticker: ProviderResult(status=ProviderStatus.SKIPPED, message="FINNHUB_API_KEY not set"),
    )
    monkeypatch.setattr(
        "src.providers.yahoo.YahooEstimateProvider.get_earnings_calendar",
        lambda self, ticker: ProviderResult(status=ProviderStatus.ERROR, message="unavailable"),
    )

    result = runner.invoke(app, ["data", "catalysts", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert len(out["catalysts"]) == 1
    assert out["calendar_status"] == "DEGRADED"


def test_catalysts_command_falls_back_to_finnhub(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setattr(
        "src.providers.alpha_vantage.AlphaVantageEstimateProvider.get_earnings_calendar",
        lambda self, ticker, horizon="12month": ProviderResult(status=ProviderStatus.ERROR, message="quota"),
    )
    monkeypatch.setattr(
        "src.providers.finnhub.FinnhubEarningsProvider.get_earnings_calendar",
        lambda self, ticker: ProviderResult(status=ProviderStatus.OK, data={"rows": [{
            "symbol": "NVDA", "name": None, "report_date": "2026-11-19",
            "fiscal_date_ending": None, "estimate": 1.2,
            "currency": "USD", "time_of_day": "amc",
        }]}),
    )

    result = runner.invoke(app, ["data", "catalysts", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["calendar_status"] == "OK"
    assert out["calendar_source"] == "finnhub"
    assert out["catalysts"][0]["event_type"] == "earnings"


def test_save_analysis_command_inserts_and_get_latest_analysis_reads_it_back(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setattr("src.services.evidence.build_evidence", lambda con, ticker: {
        "quality": {"can_decide": True},
    })

    save_result = runner.invoke(app, [
        "analysis", "save", "NVDA",
        "--decision", "ACCUMULATE", "--confidence", "0.72", "--expected-return", "0.17",
        "--expected-return-horizon-months", "24", "--expected-return-method", "BASE_CASE_TARGET",
        "--expected-return-basis", "PRICE_RETURN", "--price", "214.72",
        "--thesis-json", '["Inference demand underestimated"]',
        "--variant-perception-json", '{"variant_perception": "..."}',
        "--invalidation-json", '["Two consecutive downward revenue revisions"]',
        "--bull-value", "260", "--base-value", "230", "--bear-value", "170",
    ])
    assert save_result.exit_code == 0
    assert json.loads(save_result.stdout)["saved"] is True

    read_result = runner.invoke(app, ["analysis", "latest", "NVDA"])
    assert read_result.exit_code == 0
    out = json.loads(read_result.stdout)
    assert out["decision"] == "ACCUMULATE"
    assert out["expected_return_horizon_months"] == 24
    assert out["expected_return_method"] == "BASE_CASE_TARGET"
    assert out["expected_return_basis"] == "PRICE_RETURN"
    assert out["expected_return_annualized"] == pytest.approx(1.17 ** 0.5 - 1)
    assert json.loads(out["thesis_json"]) == ["Inference demand underestimated"]


def test_save_analysis_command_rejects_invalid_decision(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    result = runner.invoke(app, [
        "analysis", "save", "NVDA",
        "--decision", "MOON", "--confidence", "0.5", "--expected-return", "0.1",
        "--expected-return-horizon-months", "12", "--expected-return-method", "OTHER",
        "--expected-return-basis", "PRICE_RETURN", "--price", "200",
        "--thesis-json", "[]", "--variant-perception-json", "{}", "--invalidation-json", "[]",
    ])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_save_analysis_command_blocks_directional_record_when_research_only(tmp_path, monkeypatch):
    monkeypatch.setattr("src.cli.common.DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.setattr("src.services.evidence.build_evidence", lambda con, ticker: {
        "quality": {
            "can_decide": False,
            "can_research": True,
        },
    })

    result = runner.invoke(app, [
        "analysis", "save", "NVDA",
        "--decision", "HOLD", "--confidence", "0.5", "--expected-return", "0.1",
        "--expected-return-horizon-months", "12", "--expected-return-method", "OTHER",
        "--expected-return-basis", "PRICE_RETURN", "--price", "200",
        "--thesis-json", "[]", "--variant-perception-json", "{}", "--invalidation-json", "[]",
    ])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "RESEARCH_ONLY"


def test_get_latest_analysis_returns_no_history_when_empty(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    result = runner.invoke(app, ["analysis", "latest", "NVDA"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "NO_HISTORY"


def test_analysis_history_command_lists_past_analyses_most_recent_first(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc), price=170.0,
        decision=Decision.WATCH, confidence=0.5, expected_return=0.05,
        thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
    ))
    repository.insert_investment_analysis(con, InvestmentAnalysisRow(
        ticker="NVDA", created_at=datetime(2026, 8, 20, tzinfo=timezone.utc), price=214.0,
        decision=Decision.ACCUMULATE, confidence=0.72, expected_return=0.17,
        thesis_json="[]", variant_perception_json="{}", invalidation_json="[]",
    ))
    con.close()

    result = runner.invoke(app, ["analysis", "history", "NVDA"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert [a["decision"] for a in out["history"]] == ["ACCUMULATE", "WATCH"]


def test_analysis_history_command_empty_returns_empty_list(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    result = runner.invoke(app, ["analysis", "history", "NVDA"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["history"] == []


def test_change_since_command_computes_price_and_consensus_deltas(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    con = get_connection(db_path)
    migrate(con)
    for d, close in [("2026-07-22", 195.0), ("2026-08-22", 214.72)]:
        con.execute(
            "INSERT INTO prices VALUES (?, ?, 200, 200, 200, ?, 1000, 'yahoo_finance', NULL, ?, ?)",
            ["NVDA", date.fromisoformat(d), close, datetime.now(timezone.utc), date.fromisoformat(d)],
        )
    for dt, eps in [(datetime(2026, 7, 1, tzinfo=timezone.utc), 4.00), (datetime(2026, 8, 22, tzinfo=timezone.utc), 4.20)]:
        repository.insert_estimate_snapshot(con, EstimateSnapshotRow(
            ticker="NVDA", snapshot_at=dt, fiscal_period="2027-01-31", eps_mean=eps, revenue_mean=165000000000.0,
            provenance=Provenance(source="alpha_vantage", retrieved_at=dt, as_of_date=dt.date()),
        ))
    con.close()

    result = runner.invoke(app, ["analysis", "change-since", "NVDA", "--since-date", "2026-07-22"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["ticker"] == "NVDA"
    assert out["price_then"] == 195.0
    assert out["price_now"] == 214.72
    assert out["eps_then"] == 4.00
    assert out["eps_now"] == 4.20


def test_change_since_command_errors_without_stored_prices(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)

    result = runner.invoke(app, ["analysis", "change-since", "NVDA", "--since-date", "2026-07-22"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_doctor_fails_commercial_mode_without_licenses(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setenv("THESIS_LEDGER_USAGE", "commercial")
    monkeypatch.delenv("LICENSED_DATA_PROVIDERS", raising=False)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    out = json.loads(result.stdout)
    assert out["status"] == "FAIL"
    assert len(out["failures"]) == 3


def test_doctor_warns_on_empty_personal_database(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr("src.cli.common.DB_PATH", db_path)
    monkeypatch.setenv("THESIS_LEDGER_USAGE", "personal")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "WARN"
