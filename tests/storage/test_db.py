import duckdb
import pytest
from datetime import date, datetime

from src.storage.db import MIGRATIONS_DIR, get_connection, migrate

EXPECTED_TABLES = {
    "companies", "prices", "fundamentals", "estimate_snapshots",
    "guidance_snapshots", "investment_analysis", "catalysts",
    "fundamental_snapshots",
    "macro_snapshots",
}


@pytest.fixture
def con(tmp_path):
    db_path = tmp_path / "test.duckdb"
    connection = get_connection(db_path)
    migrate(connection)
    yield connection
    connection.close()


def test_migrate_creates_all_tables(con):
    rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    table_names = {r[0] for r in rows}
    assert EXPECTED_TABLES.issubset(table_names)


def test_migrate_is_idempotent(con):
    migrate(con)  # running twice must not raise
    rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    assert {r[0] for r in rows}.issuperset(EXPECTED_TABLES)
    versions = con.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert versions == [
        ("001_init.sql",), ("002_holdings.sql",), ("003_production_safety.sql",),
        ("004_macro_snapshots.sql",), ("005_macro_percentile.sql",),
        ("006_provider_revision_history.sql",),
        ("007_expected_return_metadata.sql",),
    ]


def test_expected_return_metadata_migration_preserves_legacy_rows(tmp_path):
    connection = get_connection(tmp_path / "legacy-analysis.duckdb")
    connection.execute((MIGRATIONS_DIR / "001_init.sql").read_text())
    connection.execute(
        """
        INSERT INTO investment_analysis (
            ticker, created_at, price, decision, confidence, expected_return,
            thesis_json, variant_perception_json, invalidation_json
        ) VALUES ('NVDA', current_timestamp, 100, 'HOLD', 0.5, 0.1, '[]', '{}', '[]')
        """
    )

    migrate(connection)
    row = connection.execute(
        """
        SELECT expected_return, expected_return_horizon_months,
               expected_return_method, expected_return_annualized,
               expected_return_basis
        FROM investment_analysis
        """
    ).fetchone()
    assert row == (0.1, None, None, None, None)
    connection.close()


def test_production_safety_migration_preserves_legacy_fundamentals(tmp_path):
    connection = get_connection(tmp_path / "legacy.duckdb")
    connection.execute((MIGRATIONS_DIR / "001_init.sql").read_text())
    connection.execute((MIGRATIONS_DIR / "002_holdings.sql").read_text())
    connection.execute(
        """
        INSERT INTO fundamentals (
            ticker, period, reported_at, revenue, source, retrieved_at, as_of_date
        ) VALUES ('NVDA', '2025-01-31', ?, 100.0, 'sec_edgar', ?, ?)
        """,
        [date(2025, 2, 26), datetime(2025, 2, 26), date(2025, 1, 31)],
    )

    migrate(connection)
    migrate(connection)

    rows = connection.execute(
        "SELECT filed_at, revenue, form FROM fundamental_snapshots WHERE ticker='NVDA'"
    ).fetchall()
    assert rows == [(date(2025, 2, 26), 100.0, "LEGACY")]
    connection.close()
