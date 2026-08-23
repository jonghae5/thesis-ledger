import os
from typing import Optional


RESTRICTED_FOR_COMMERCIAL_USE = {"yahoo_finance", "alpha_vantage", "finnhub"}


def commercial_provider_error(provider: str) -> Optional[str]:
    usage = os.environ.get("THESIS_LEDGER_USAGE", "personal").strip().lower()
    if usage not in {"personal", "commercial"}:
        return "THESIS_LEDGER_USAGE must be 'personal' or 'commercial'"
    if usage != "commercial" or provider not in RESTRICTED_FOR_COMMERCIAL_USE:
        return None
    licensed = {
        item.strip().lower()
        for item in os.environ.get("LICENSED_DATA_PROVIDERS", "").split(",")
        if item.strip()
    }
    if provider not in licensed:
        return (
            f"{provider} is blocked in commercial mode until a commercial data "
            "license is recorded in LICENSED_DATA_PROVIDERS"
        )
    return None
