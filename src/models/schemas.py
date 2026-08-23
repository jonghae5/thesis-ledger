from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.models.enums import Decision, ProviderStatus


class Provenance(BaseModel):
    source: str
    source_url: Optional[str] = None
    retrieved_at: datetime
    as_of_date: date


class CompanyRow(BaseModel):
    ticker: str = Field(pattern=r"^[A-Z0-9.-]{1,15}$")
    name: str
    cik: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None


class HoldingRow(BaseModel):
    ticker: str = Field(pattern=r"^[A-Z0-9.-]{1,15}$")
    shares: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    opened_at: date
    sector: Optional[str] = None


class PriceRow(BaseModel):
    ticker: str = Field(pattern=r"^[A-Z0-9.-]{1,15}$")
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(ge=0)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_ohlc(self):
        if min(self.open, self.high, self.low, self.close) < 0:
            raise ValueError("OHLC prices must be non-negative")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high must be at least open/low/close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low must be at most open/high/close")
        return self


class FundamentalSnapshotRow(BaseModel):
    ticker: str
    period: str
    filed_at: date
    accession: str
    form: str
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    operating_cashflow: Optional[float] = None
    capex: Optional[float] = None
    fcf: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None
    shares: Optional[float] = None
    currency: Optional[str] = None
    provenance: Provenance


class EstimateSnapshotRow(BaseModel):
    ticker: str
    snapshot_at: datetime
    fiscal_period: str
    eps_mean: Optional[float] = None
    eps_high: Optional[float] = None
    eps_low: Optional[float] = None
    revenue_mean: Optional[float] = None
    revenue_high: Optional[float] = None
    revenue_low: Optional[float] = None
    analyst_count: Optional[int] = Field(default=None, ge=0)
    eps_mean_7d_ago: Optional[float] = None
    eps_mean_30d_ago: Optional[float] = None
    eps_mean_90d_ago: Optional[float] = None
    revenue_mean_7d_ago: Optional[float] = None
    revenue_mean_30d_ago: Optional[float] = None
    revenue_mean_90d_ago: Optional[float] = None
    provenance: Provenance

    @model_validator(mode="after")
    def validate_estimate_ranges(self):
        for name, low, mean_value, high in [
            ("eps", self.eps_low, self.eps_mean, self.eps_high),
            ("revenue", self.revenue_low, self.revenue_mean, self.revenue_high),
        ]:
            present = [v for v in (low, mean_value, high) if v is not None]
            if len(present) == 3 and not low <= mean_value <= high:
                raise ValueError(f"{name} estimate must satisfy low <= mean <= high")
        return self


class MacroSnapshotRow(BaseModel):
    indicator: str = Field(pattern=r"^[A-Z0-9_]{1,40}$")
    snapshot_at: datetime
    observation_date: date
    value: float
    unit: str
    source_type: Literal["FACT", "MODEL_OUTPUT"]
    transformation: str
    reference_date: Optional[date] = None
    reference_value: Optional[float] = None
    percentile_5y: Optional[float] = Field(default=None, ge=0, le=100)
    source: str
    source_url: Optional[str] = None
    retrieved_at: datetime

    @model_validator(mode="after")
    def validate_reference_pair(self):
        if (self.reference_date is None) != (self.reference_value is None):
            raise ValueError("reference_date and reference_value must be provided together")
        return self


class GuidanceSnapshotRow(BaseModel):
    ticker: str
    snapshot_at: datetime
    revenue_low: Optional[float] = None
    revenue_high: Optional[float] = None
    margin_guidance: Optional[float] = Field(default=None, ge=0, le=1)
    capex_guidance: Optional[float] = Field(default=None, ge=0)
    source_filing: str
    source_date: date
    retrieved_at: datetime

    @model_validator(mode="after")
    def validate_guidance_range(self):
        if self.revenue_low is not None and self.revenue_low < 0:
            raise ValueError("revenue_low must be non-negative")
        if self.revenue_high is not None and self.revenue_high < 0:
            raise ValueError("revenue_high must be non-negative")
        if (
            self.revenue_low is not None and self.revenue_high is not None
            and self.revenue_low > self.revenue_high
        ):
            raise ValueError("guidance must satisfy revenue_low <= revenue_high")
        return self


class InvestmentAnalysisRow(BaseModel):
    id: Optional[int] = None
    ticker: str
    created_at: datetime
    price: float = Field(gt=0)
    decision: Decision
    confidence: float = Field(ge=0, le=1)
    expected_return: float = Field(gt=-1)
    expected_return_horizon_months: Optional[int] = Field(default=None, gt=0)
    expected_return_method: Optional[Literal[
        "PROBABILITY_WEIGHTED_SCENARIO", "BASE_CASE_TARGET", "DCF_IRR", "OTHER"
    ]] = None
    expected_return_annualized: Optional[float] = Field(default=None, gt=-1)
    expected_return_basis: Optional[Literal["PRICE_RETURN", "TOTAL_RETURN"]] = None
    bull_value: Optional[float] = None
    base_value: Optional[float] = None
    bear_value: Optional[float] = None
    thesis_json: str
    variant_perception_json: str
    invalidation_json: str
    run_id: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    prompt_version: Optional[str] = None
    input_snapshot_json: Optional[str] = None
    assumptions_json: Optional[str] = None

    @model_validator(mode="after")
    def validate_expected_return_metadata(self):
        metadata = (
            self.expected_return_horizon_months,
            self.expected_return_method,
            self.expected_return_annualized,
            self.expected_return_basis,
        )
        if any(value is not None for value in metadata) and not all(value is not None for value in metadata):
            raise ValueError("expected return metadata must be provided together")
        if self.expected_return_horizon_months is not None:
            annualized = (1 + self.expected_return) ** (12 / self.expected_return_horizon_months) - 1
            if abs(annualized - self.expected_return_annualized) > 1e-9:
                raise ValueError("expected_return_annualized does not match expected_return and horizon")
        return self

    @model_validator(mode="after")
    def validate_scenario_order(self):
        values = (self.bear_value, self.base_value, self.bull_value)
        if all(value is not None for value in values) and not self.bear_value <= self.base_value <= self.bull_value:
            raise ValueError("scenario values must satisfy bear_value <= base_value <= bull_value")
        return self


class CatalystRow(BaseModel):
    ticker: str = Field(pattern=r"^[A-Z0-9.-]{1,15}$")
    event_date: date
    event_type: str
    description: str = Field(min_length=1)
    importance: Literal["HIGH", "MED", "LOW"]


class ProviderResult(BaseModel):
    status: ProviderStatus
    data: Optional[dict] = None
    message: Optional[str] = None
