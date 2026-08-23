import hashlib
import json
import uuid
from datetime import date, datetime, timezone

from src.services.research import (
    DEFAULT_MAX_PRICE_AGE_DAYS,
    business_quality_payload,
    expectations_payload,
    fundamentals_payload,
    macro_payload,
    market_payload,
    resolve_estimate_period,
    reverse_dcf_payload,
    revisions_payload,
    valuation_payload,
)
from src.storage import repository
from src.tools.change import compute_change_since


def _section(builder) -> dict:
    try:
        return {"status": "OK", **builder()}
    except ValueError as exc:
        return {"status": "MISSING", "message": str(exc)}


def _guidance_section(con, ticker: str) -> dict:
    guidance = repository.get_latest_guidance_snapshot(con, ticker)
    if not guidance:
        return {"status": "MISSING", "message": "no stored management guidance"}
    source_date = guidance["source_date"]
    if isinstance(source_date, str):
        source_date = date.fromisoformat(source_date)
    age_days = (date.today() - source_date).days
    section = {"status": "OK", **guidance, "age_days": age_days}
    if age_days > 120:
        section["status"] = "STALE"
        section["message"] = f"management guidance is {age_days} days old"
    return section


def _expectation_anchors(sections: dict) -> list[str]:
    anchors = []
    has_fresh_consensus = sections["expectations"]["status"] == "OK"
    has_revision_signal = (
        sections["revisions"]["status"] == "OK"
        and sections["revisions"].get("revision_score") is not None
    )
    if has_fresh_consensus and has_revision_signal:
        anchors.append("CONSENSUS_REVISION")

    guidance = sections["guidance"]
    guidance_dimensions = (
        guidance.get("fiscal_period"), guidance.get("guidance_scope"),
        guidance.get("currency"), guidance.get("value_unit"),
    )
    has_guided_metric = any(
        guidance.get(field) is not None
        for field in ("revenue_low", "revenue_high", "margin_guidance", "capex_guidance")
    )
    if (
        guidance["status"] == "OK"
        and all(value is not None for value in guidance_dimensions)
        and has_guided_metric
        and sections["implied_expectations"]["status"] == "OK"
    ):
        anchors.append("GUIDANCE_VS_PRICE_IMPLIED")
    return anchors


def _expectations_section(con, ticker: str) -> dict:
    section = _section(lambda: expectations_payload(con, ticker))
    if section["status"] != "OK":
        return section
    snapshot_at = datetime.fromisoformat(section["snapshot_at"])
    # DuckDB TIMESTAMP returns a timezone-naive local wall time even when an
    # aware datetime was inserted. Freshness is day-based, so compare calendar
    # dates and never report a negative age because of that conversion.
    age_days = max(0, (date.today() - snapshot_at.date()).days)
    section["age_days"] = age_days
    if age_days > 2:
        section["status"] = "STALE"
        section["message"] = (
            f"consensus snapshot is {age_days} days old - run 'data expectations'"
        )
    return section


def _quality_report(sections: dict) -> dict:
    missing = [name for name, section in sections.items() if section["status"] != "OK"]
    research_core = ("market", "fundamentals", "valuation")
    can_research = all(sections[name]["status"] == "OK" for name in research_core)
    expectation_anchors = _expectation_anchors(sections)
    can_decide = can_research and bool(expectation_anchors)
    cannot_conclude = []
    warnings = []

    if sections["expectations"]["status"] != "OK":
        cannot_conclude.extend(["forward valuation", "consensus gap"])
    if sections["revisions"]["status"] != "OK" or sections["revisions"].get("revision_score") is None:
        cannot_conclude.append("consensus revision trend")
    if sections["implied_expectations"]["status"] != "OK":
        cannot_conclude.append("price-implied growth")
    if sections["macro"]["status"] != "OK":
        cannot_conclude.append("macro-sensitive scenario calibration")
        warnings.extend(sections["macro"].get("warnings", []))
    if sections["catalysts"]["status"] != "OK" or not sections["catalysts"].get("items"):
        warnings.append("no stored catalysts; upcoming event coverage may be incomplete")
    if sections["guidance"]["status"] != "OK":
        warnings.append("no stored management guidance")

    fundamentals = sections["fundamentals"]
    if fundamentals["status"] == "OK":
        for field in ("fcf_margin", "revenue_growth", "net_debt"):
            if fundamentals.get(field) is None:
                warnings.append(f"fundamentals.{field} is unavailable")

    business_quality = sections["business_quality"]
    if business_quality["status"] == "OK":
        warnings.extend(
            f"business_quality: {warning}"
            for warning in business_quality.get("coverage", {}).get("warnings", [])
        )

    if not can_research:
        completeness = "INSUFFICIENT"
    elif can_decide and not missing and not cannot_conclude:
        completeness = "COMPLETE"
    else:
        completeness = "PARTIAL"
    return {
        "completeness": completeness,
        "can_research": can_research,
        "can_decide": can_decide,
        "expectation_anchors": expectation_anchors,
        "missing": missing,
        "cannot_conclude": sorted(set(cannot_conclude)),
        "warnings": warnings,
    }


def build_evidence(con, ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    ticker = ticker.upper()
    sections = {
        "market": _section(lambda: market_payload(con, ticker, max_price_age_days)),
        "fundamentals": _section(lambda: fundamentals_payload(con, ticker)),
        "business_quality": _section(lambda: business_quality_payload(con, ticker)),
        "expectations": _expectations_section(con, ticker),
        "revisions": _section(lambda: revisions_payload(con, ticker)),
        "valuation": _section(lambda: valuation_payload(con, ticker, max_price_age_days)),
        "implied_expectations": _section(
            lambda: reverse_dcf_payload(con, ticker, max_price_age_days=max_price_age_days)
        ),
        "macro": macro_payload(con),
        "guidance": _guidance_section(con, ticker),
        "catalysts": {
            "status": "OK",
            "items": repository.get_catalysts(con, ticker, since=date.today()),
        },
    }
    return {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality": _quality_report(sections),
        "sections": sections,
    }


def compare_evidence(evidence_items: list[dict]) -> dict:
    if len(evidence_items) < 2:
        raise ValueError("compare requires at least two tickers")
    rows = []
    price_dates = set()
    filing_dates = set()
    currencies = set()
    for evidence in evidence_items:
        sections = evidence["sections"]
        market = sections["market"]
        fundamentals = sections["fundamentals"]
        business_quality = sections["business_quality"]
        expectations = sections["expectations"]
        revisions = sections["revisions"]
        valuation = sections["valuation"]
        implied = sections["implied_expectations"]
        price_dates.add(market.get("as_of_date"))
        filing_dates.add(fundamentals.get("data_filed_at"))
        currencies.add(fundamentals.get("currency"))
        rows.append({
            "ticker": evidence["ticker"],
            "completeness": evidence["quality"]["completeness"],
            "price": market.get("price"),
            "price_as_of_date": market.get("as_of_date"),
            "momentum_3m": market.get("momentum_3m"),
            "volatility_60d": market.get("volatility_60d"),
            "revenue_growth": fundamentals.get("revenue_growth"),
            "quarterly_revenue_growth_yoy": fundamentals.get("ttm", {}).get("revenue_growth_yoy"),
            "fcf_margin": fundamentals.get("fcf_margin"),
            "ttm_fcf_margin": fundamentals.get("ttm", {}).get("fcf_margin"),
            "net_debt": fundamentals.get("net_debt"),
            "annual_revenue_cagr": business_quality.get(
                "growth_and_reinvestment", {},
            ).get("revenue_cagr", {}).get("value"),
            "gross_margin_latest": business_quality.get(
                "profitability", {},
            ).get("gross_margin", {}).get("latest"),
            "operating_margin_latest": business_quality.get(
                "profitability", {},
            ).get("operating_margin", {}).get("latest"),
            "annual_fcf_margin_latest": business_quality.get(
                "cash_generation", {},
            ).get("fcf_margin", {}).get("latest"),
            "shares_cagr": business_quality.get(
                "shareholder_and_balance_sheet", {},
            ).get("shares_cagr", {}).get("value"),
            "roic_latest": business_quality.get(
                "returns_on_capital", {},
            ).get("roic", {}).get("latest"),
            "sbc_to_revenue_latest": business_quality.get(
                "capital_allocation", {},
            ).get("sbc_to_revenue", {}).get("latest"),
            "working_capital_to_revenue_latest": business_quality.get(
                "working_capital", {},
            ).get("working_capital_to_revenue", {}).get("latest"),
            "goodwill_to_assets_latest": business_quality.get(
                "ma_dependence", {},
            ).get("goodwill_to_assets", {}).get("latest"),
            "interest_coverage_latest": business_quality.get(
                "shareholder_and_balance_sheet", {},
            ).get("interest_coverage", {}).get("latest"),
            "fundamentals_filed_at": fundamentals.get("data_filed_at"),
            "currency": fundamentals.get("currency"),
            "eps_consensus": expectations.get("eps", {}).get("mean"),
            "revision_score": revisions.get("revision_score"),
            "trailing_pe": valuation.get("trailing_pe"),
            "forward_pe": valuation.get("forward_pe"),
            "ev_to_revenue_trailing": valuation.get("ev_to_revenue_trailing"),
            "fcf_yield_trailing": valuation.get("fcf_yield_trailing"),
            "implied_revenue_cagr": implied.get("implied_revenue_cagr"),
            "financial_basis": valuation.get("financial_basis"),
        })
    warnings = []
    if len(price_dates - {None}) > 1:
        warnings.append("price dates differ across tickers")
    if len(filing_dates - {None}) > 1:
        warnings.append("fundamental filing dates differ across tickers")
    if len(currencies - {None}) > 1:
        warnings.append("currencies differ across tickers; raw values are not directly comparable")
    unusable = [
        evidence["ticker"] for evidence in evidence_items
        if not evidence["quality"]["can_research"]
    ]
    if unusable:
        warnings.append(f"insufficient evidence for: {', '.join(unusable)}")
    return {
        "can_research": bool(len(evidence_items) - len(unusable)),
        "can_decide": all(evidence["quality"]["can_decide"] for evidence in evidence_items),
        "tickers": [row["ticker"] for row in rows],
        "rows": rows,
        "warnings": warnings,
    }


def freeze_evidence_bundle(con, ticker: str, evidence: dict) -> dict:
    """Persist the exact evidence package used for one independent assessment."""
    ticker = ticker.upper()
    if evidence.get("ticker") != ticker:
        raise ValueError("evidence ticker does not match requested ticker")
    evidence_json = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    evidence_sha256 = hashlib.sha256(evidence_json.encode()).hexdigest()
    bundle_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    repository.insert_evidence_bundle(
        con, bundle_id, ticker, created_at, evidence_sha256, evidence_json,
    )
    return {
        "bundle_id": bundle_id,
        "ticker": ticker,
        "created_at": created_at.isoformat(),
        "evidence_sha256": evidence_sha256,
    }


def load_evidence_bundle(con, ticker: str, bundle_id: str) -> dict:
    ticker = ticker.upper()
    row = repository.get_evidence_bundle(con, bundle_id)
    if row is None:
        raise ValueError(f"evidence bundle not found: {bundle_id}")
    if row["ticker"] != ticker:
        raise ValueError("evidence bundle ticker does not match requested ticker")
    actual_hash = hashlib.sha256(row["evidence_json"].encode()).hexdigest()
    if actual_hash != row["evidence_sha256"]:
        raise ValueError("evidence bundle hash mismatch")
    return {**row, "evidence": json.loads(row["evidence_json"])}


def prepare_current(
    con,
    ticker: str,
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
    freeze: bool = False,
) -> dict:
    """Build current evidence without exposing prior conclusions."""
    ticker = ticker.upper()
    evidence = build_evidence(con, ticker, max_price_age_days)
    bundle = None
    if freeze and evidence["quality"]["can_research"]:
        bundle = freeze_evidence_bundle(con, ticker, evidence)
    return {
        "ticker": ticker,
        "independent_assessment": True,
        "evidence_bundle": bundle,
        "evidence": evidence,
    }


def _changes_since_previous(con, ticker: str, previous: dict | None) -> dict | None:
    if previous is None:
        return None
    try:
        price_rows = repository.get_latest_prices(con, ticker, limit=500)
        all_estimates = repository.get_estimate_snapshots(con, ticker, limit=200)
        period = resolve_estimate_period(all_estimates) if all_estimates else None
        estimate_rows = repository.get_estimate_snapshots(
            con, ticker, limit=200, fiscal_period=period,
        ) if period else []
        return {
            "status": "OK",
            "fiscal_period": period,
            **compute_change_since(
                price_rows,
                estimate_rows,
                since_date=date.fromisoformat(previous["created_at"][:10]),
            ),
        }
    except ValueError as exc:
        return {"status": "MISSING", "message": str(exc)}


def compare_prior(con, ticker: str, evidence_bundle_id: str) -> dict:
    """Reveal prior analysis only after an independent evidence bundle exists."""
    ticker = ticker.upper()
    bundle = load_evidence_bundle(con, ticker, evidence_bundle_id)
    previous = repository.get_latest_investment_analysis(con, ticker)
    return {
        "ticker": ticker,
        "evidence_bundle": {
            key: bundle[key]
            for key in ("bundle_id", "ticker", "created_at", "evidence_sha256")
        },
        "current_evidence": bundle["evidence"],
        "previous_analysis": previous,
        "changes_since_previous": _changes_since_previous(con, ticker, previous),
    }


def prepare_update(con, ticker: str, max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS) -> dict:
    ticker = ticker.upper()
    evidence = build_evidence(con, ticker, max_price_age_days)
    previous = repository.get_latest_investment_analysis(con, ticker)
    return {
        "ticker": ticker,
        "previous_analysis": previous,
        "changes_since_previous": _changes_since_previous(con, ticker, previous),
        "evidence": evidence,
    }
