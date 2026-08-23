from typing import List


def _calendar_row_to_catalyst(row: dict) -> dict:
    estimate = row.get("estimate")
    estimate_note = f", EPS est {estimate}" if estimate is not None else ""
    return {
        "event_date": row["report_date"],
        "event_type": "earnings",
        "description": f"{row.get('symbol', '')} earnings (FY period ending {row.get('fiscal_date_ending')}){estimate_note}",
        "importance": "HIGH",
    }


def merge_catalysts(stored: List[dict], calendar_rows: List[dict]) -> List[dict]:
    stored_earnings_dates = {r["event_date"] for r in stored if r["event_type"] == "earnings"}

    converted = [
        _calendar_row_to_catalyst(row)
        for row in calendar_rows
        if row.get("report_date") and row["report_date"] not in stored_earnings_dates
    ]

    merged = list(stored) + converted
    return sorted(merged, key=lambda r: r["event_date"])
