import os
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import httpx

from src.models.enums import ProviderStatus
from src.models.schemas import ProviderResult
from src.providers.cache import cached_fetch

SEC_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

US_GAAP_TAGS: Dict[str, List[str]] = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "operating_cashflow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "debt": [
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtNoncurrent",
    ],
    "shares": ["CommonStockSharesOutstanding"],
    "assets": ["Assets"],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "short_term_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
    "current_debt": [
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtCurrent",
    ],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
    ],
    "income_tax_expense": ["IncomeTaxExpenseBenefit"],
    "sbc": ["ShareBasedCompensation"],
    "share_repurchases": ["PaymentsForRepurchaseOfCommonStock"],
    "accounts_receivable": ["AccountsReceivableNetCurrent"],
    "inventory": ["InventoryNet"],
    "accounts_payable": ["AccountsPayableCurrent"],
    "goodwill": ["Goodwill"],
    "acquisition_cash_paid": [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesGross",
    ],
    "interest_expense": [
        "InterestExpenseNonoperating",
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestExpenseDebtExcludingAmortization",
    ],
}


class SecFilingProvider:
    def __init__(self, contact_email: Optional[str] = None):
        self._contact_email = contact_email

    def _contact(self) -> str:
        email = self._contact_email if self._contact_email is not None else os.environ.get("SEC_CONTACT_EMAIL", "")
        if not email:
            raise RuntimeError("SEC_CONTACT_EMAIL not set - required by SEC User-Agent policy")
        return email

    def _headers(self) -> dict:
        return {"User-Agent": f"thesis-ledger {self._contact()}"}

    def _get_cik(self, ticker: str) -> Optional[str]:
        def _fetch_tickers() -> dict:
            response = httpx.get(TICKERS_URL, headers=self._headers(), timeout=10)
            response.raise_for_status()
            return response.json()

        data = cached_fetch(
            "sec", "company_tickers", 86400,
            _fetch_tickers,
        )
        for row in data.values():
            if row["ticker"].upper() == ticker.upper():
                return str(row["cik_str"]).zfill(10)
        return None

    def get_submissions(self, ticker: str) -> ProviderResult:
        try:
            cik = self._get_cik(ticker)
            if cik is None:
                return ProviderResult(status=ProviderStatus.ERROR, message=f"CIK not found for {ticker}")
            resp = httpx.get(f"{SEC_BASE}/submissions/CIK{cik}.json", headers=self._headers(), timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        return ProviderResult(status=ProviderStatus.OK, data=payload)

    def get_company_facts(self, ticker: str) -> ProviderResult:
        try:
            cik = self._get_cik(ticker)
            if cik is None:
                return ProviderResult(status=ProviderStatus.ERROR, message=f"CIK not found for {ticker}")
            resp = httpx.get(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json", headers=self._headers(), timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        return ProviderResult(status=ProviderStatus.OK, data=payload)

    def get_guidance_sources(
        self, ticker: str, lookback_days: int = 365, limit: int = 8,
    ) -> ProviderResult:
        """Discover earnings-release documents without interpreting guidance."""
        if not 1 <= lookback_days <= 3650:
            return ProviderResult(
                status=ProviderStatus.ERROR,
                message="lookback_days must be between 1 and 3650",
            )
        if not 1 <= limit <= 50:
            return ProviderResult(
                status=ProviderStatus.ERROR,
                message="limit must be between 1 and 50",
            )

        submissions = self.get_submissions(ticker)
        if submissions.status != ProviderStatus.OK:
            return submissions
        try:
            payload = submissions.data or {}
            cik = str(payload.get("cik", "")).lstrip("0")
            if not cik:
                raise ValueError("SEC submissions response has no CIK")
            recent = payload.get("filings", {}).get("recent", {})
            fields = (
                "accessionNumber", "filingDate", "form", "primaryDocument", "items",
            )
            accession_numbers = recent.get("accessionNumber", [])
            filings = []
            for index in range(len(accession_numbers)):
                filing = {}
                for field in fields:
                    values = recent.get(field, [])
                    filing[field] = values[index] if index < len(values) else None
                filings.append(filing)
            cutoff = date.today() - timedelta(days=lookback_days)
            earnings_filings = sorted(
                (
                    filing for filing in filings
                    if filing.get("form") == "8-K"
                    and "2.02" in (filing.get("items") or "")
                    and filing.get("filingDate")
                    and date.fromisoformat(filing["filingDate"]) >= cutoff
                ),
                key=lambda filing: filing["filingDate"],
                reverse=True,
            )[:limit]

            rows = []
            for filing in earnings_filings:
                accession = filing["accessionNumber"]
                compact_accession = accession.replace("-", "")
                base_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{compact_accession}"
                )
                rows.append({
                    "filing_date": filing["filingDate"],
                    "accession": accession,
                    "form": filing["form"],
                    "items": filing.get("items"),
                    "filing_index_url": f"{base_url}/{accession}-index.html",
                    "primary_document_url": (
                        f"{base_url}/{filing['primaryDocument']}"
                        if filing.get("primaryDocument") else None
                    ),
                })
        except Exception as exc:
            return ProviderResult(status=ProviderStatus.ERROR, message=str(exc))
        return ProviderResult(status=ProviderStatus.OK, data={
            "ticker": ticker.upper(),
            "classification": "CANDIDATE_SOURCE",
            "filings": rows,
            "warning": "filings are source candidates; Python does not infer or save guidance",
        })


_FLOW_FIELDS = {
    "revenue", "gross_profit", "operating_income", "net_income",
    "operating_cashflow", "capex", "pretax_income", "income_tax_expense",
    "sbc", "share_repurchases", "acquisition_cash_paid", "interest_expense",
}


def _supported_filing_fact(field: str, item: dict) -> bool:
    form = item.get("form")
    if form not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}:
        return False
    if field not in _FLOW_FIELDS:
        return not item.get("start")
    start = item.get("start")
    end = item.get("end")
    if not start or not end:
        return False
    try:
        duration = (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return False
    if form.startswith("10-K"):
        return 340 <= duration <= 380
    # Keep discrete quarters only; cumulative six/nine-month 10-Q facts would
    # otherwise be mixed with quarterly and annual values.
    return 75 <= duration <= 105


def extract_fundamental_snapshots(facts_json: dict, ticker: str, retrieved_at: str) -> List[dict]:
    """Extract filing-time snapshots without pretending period-end was report time.

    Rows are keyed by accession and period, so later filings that restate a
    comparative period remain separate point-in-time observations.
    """
    us_gaap = facts_json.get("facts", {}).get("us-gaap", {})
    grouped: Dict[Tuple[str, str, str, str], dict] = {}
    field_priority: Dict[Tuple[Tuple[str, str, str, str], str], int] = {}

    for field, tags in US_GAAP_TAGS.items():
        expected_unit = "shares" if field == "shares" else "USD"
        for priority, tag in enumerate(tags):
            node = us_gaap.get(tag) or {}
            for unit, unit_values in node.get("units", {}).items():
                if unit != expected_unit:
                    continue
                for item in unit_values:
                    end = item.get("end")
                    filed = item.get("filed")
                    accession = item.get("accn")
                    form = item.get("form")
                    if not end or not filed or not accession or not _supported_filing_fact(field, item):
                        continue
                    key = (end, filed, accession, form)
                    row = grouped.setdefault(key, {
                        "ticker": ticker,
                        "period": end,
                        "filed_at": filed,
                        "accession": accession,
                        "form": form,
                        "fiscal_year": item.get("fy"),
                        "fiscal_period": item.get("fp"),
                        "currency": "USD",
                        "source_concepts": {},
                    })
                    priority_key = (key, field)
                    if priority <= field_priority.get(priority_key, priority):
                        row[field] = item.get("val")
                        row["source_concepts"][field] = tag
                        field_priority[priority_key] = priority

    rows = []
    for key in sorted(grouped, key=lambda k: (k[1], k[0], k[2])):
        values = grouped[key]
        ocf = values.get("operating_cashflow")
        capex = values.get("capex")
        values["fcf"] = ocf - capex if ocf is not None and capex is not None else None
        cik = str(facts_json.get("cik", "")).zfill(10)
        values.update({
            "source": "sec_edgar",
            "source_url": (
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
                if cik.strip("0") else "https://data.sec.gov/api/xbrl/companyfacts/"
            ),
            "retrieved_at": retrieved_at,
            "as_of_date": values["filed_at"],
        })
        rows.append(values)
    return rows
