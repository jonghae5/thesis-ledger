from datetime import date

import pytest

from src.models.schemas import HoldingRow
from src.storage import repository
from src.storage.db import get_connection, migrate


@pytest.fixture
def con(tmp_path):
    connection = get_connection(tmp_path / "test.duckdb")
    migrate(connection)
    yield connection
    connection.close()


def test_holdings_table_exists_after_migrate(con):
    rows = con.execute("SELECT table_name FROM information_schema.tables WHERE table_name = 'holdings'").fetchall()
    assert len(rows) == 1


def test_upsert_holding_then_upsert_again_updates_in_place(con):
    repository.upsert_holding(con, HoldingRow(ticker="NVDA", shares=10.0, avg_cost=150.0, opened_at=date(2026, 1, 15), sector="Semiconductors"))
    repository.upsert_holding(con, HoldingRow(ticker="NVDA", shares=15.0, avg_cost=160.0, opened_at=date(2026, 1, 15), sector="Semiconductors"))
    rows = repository.get_holdings(con)
    assert len(rows) == 1
    assert rows[0]["shares"] == 15.0
    assert rows[0]["avg_cost"] == 160.0


def test_get_holdings_returns_all_tickers(con):
    repository.upsert_holding(con, HoldingRow(ticker="NVDA", shares=10.0, avg_cost=150.0, opened_at=date(2026, 1, 15)))
    repository.upsert_holding(con, HoldingRow(ticker="AAPL", shares=5.0, avg_cost=200.0, opened_at=date(2026, 2, 1)))
    rows = repository.get_holdings(con)
    assert {r["ticker"] for r in rows} == {"NVDA", "AAPL"}


def test_remove_holding_returns_true_when_removed_false_when_absent(con):
    repository.upsert_holding(con, HoldingRow(ticker="NVDA", shares=10.0, avg_cost=150.0, opened_at=date(2026, 1, 15)))
    assert repository.remove_holding(con, "NVDA") is True
    assert repository.get_holdings(con) == []
    assert repository.remove_holding(con, "NVDA") is False
