from src.tools.catalysts import merge_catalysts

CALENDAR_ROWS = [
    {"symbol": "NVDA", "name": "NVIDIA Corp", "report_date": "2026-11-19",
     "fiscal_date_ending": "2026-10-31", "estimate": 1.28, "currency": "USD", "time_of_day": "post-market"},
]


def test_merge_catalysts_converts_calendar_row_to_catalyst_shape():
    merged = merge_catalysts(stored=[], calendar_rows=CALENDAR_ROWS)
    assert len(merged) == 1
    row = merged[0]
    assert row["event_date"] == "2026-11-19"
    assert row["event_type"] == "earnings"
    assert row["importance"] == "HIGH"
    assert "1.28" in row["description"]


def test_merge_catalysts_dedupes_against_manually_stored_earnings_row():
    stored = [{"event_date": "2026-11-19", "event_type": "earnings", "description": "manual note", "importance": "HIGH"}]
    merged = merge_catalysts(stored=stored, calendar_rows=CALENDAR_ROWS)
    assert len(merged) == 1
    assert merged[0]["description"] == "manual note"  # manually-stored entry wins


def test_merge_catalysts_keeps_non_earnings_stored_rows_and_sorts_by_date():
    stored = [{"event_date": "2026-09-05", "event_type": "product_launch", "description": "GPU reveal", "importance": "MED"}]
    merged = merge_catalysts(stored=stored, calendar_rows=CALENDAR_ROWS)
    assert [r["event_type"] for r in merged] == ["product_launch", "earnings"]


def test_merge_catalysts_with_no_calendar_rows_returns_stored_only():
    stored = [{"event_date": "2026-09-05", "event_type": "product_launch", "description": "GPU reveal", "importance": "MED"}]
    assert merge_catalysts(stored=stored, calendar_rows=[]) == stored
