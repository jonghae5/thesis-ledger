import pytest

from src.storage.db import get_connection, migrate

EXPECTED_TABLES = {
    "companies", "prices", "estimate_snapshots",
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
        ("001_init.sql",),
        ("002_sec_quality_inputs.sql",),
    ]
