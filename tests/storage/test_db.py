import hashlib

import pytest

from src.storage.db import MIGRATIONS_DIR, get_connection, migrate

EXPECTED_TABLES = {
    "companies", "prices", "estimate_snapshots",
    "guidance_snapshots", "investment_analysis", "catalysts",
    "fundamental_snapshots",
    "macro_snapshots",
    "evidence_bundles",
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
        ("003_evidence_bundles.sql",),
    ]


def test_evidence_bundle_migration_preserves_existing_analysis(tmp_path):
    con = get_connection(tmp_path / "legacy.duckdb")
    con.execute(
        """
        CREATE TABLE schema_migrations (
            version VARCHAR PRIMARY KEY,
            checksum VARCHAR NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    for version in ("001_init.sql", "002_sec_quality_inputs.sql"):
        sql = (MIGRATIONS_DIR / version).read_text()
        con.execute(sql)
        con.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES (?, ?)",
            [version, hashlib.sha256(sql.encode()).hexdigest()],
        )
    con.execute(
        """
        INSERT INTO investment_analysis (
            ticker, created_at, price, decision, confidence, expected_return,
            thesis_json, variant_perception_json, invalidation_json
        ) VALUES ('NVDA', current_timestamp, 100, 'HOLD', 0.5, 0.1, '[]', '{}', '[]')
        """
    )

    migrate(con)

    row = con.execute(
        "SELECT ticker, decision, evidence_bundle_id FROM investment_analysis"
    ).fetchone()
    assert row == ("NVDA", "HOLD", None)
    assert con.execute("SELECT COUNT(*) FROM evidence_bundles").fetchone()[0] == 0
    con.close()
