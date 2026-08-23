CREATE TABLE IF NOT EXISTS companies (
    ticker VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    cik VARCHAR,
    sector VARCHAR,
    industry VARCHAR,
    exchange VARCHAR
);

CREATE TABLE IF NOT EXISTS prices (
    ticker VARCHAR NOT NULL,
    date DATE NOT NULL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume BIGINT,
    source VARCHAR NOT NULL,
    source_url VARCHAR,
    retrieved_at TIMESTAMP NOT NULL,
    as_of_date DATE NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE SEQUENCE IF NOT EXISTS fundamental_snapshots_id_seq;
CREATE TABLE IF NOT EXISTS fundamental_snapshots (
    id BIGINT PRIMARY KEY DEFAULT nextval('fundamental_snapshots_id_seq'),
    ticker VARCHAR NOT NULL,
    period VARCHAR NOT NULL,
    filed_at DATE NOT NULL,
    accession VARCHAR NOT NULL,
    form VARCHAR NOT NULL,
    fiscal_year INTEGER,
    fiscal_period VARCHAR,
    revenue DOUBLE,
    gross_profit DOUBLE,
    operating_income DOUBLE,
    net_income DOUBLE,
    operating_cashflow DOUBLE,
    capex DOUBLE,
    fcf DOUBLE,
    cash DOUBLE,
    debt DOUBLE,
    shares DOUBLE,
    currency VARCHAR,
    source VARCHAR NOT NULL,
    source_url VARCHAR,
    retrieved_at TIMESTAMP NOT NULL,
    UNIQUE (ticker, accession, period)
);

CREATE SEQUENCE IF NOT EXISTS estimate_snapshots_id_seq;
CREATE TABLE IF NOT EXISTS estimate_snapshots (
    id BIGINT PRIMARY KEY DEFAULT nextval('estimate_snapshots_id_seq'),
    ticker VARCHAR NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,
    fiscal_period VARCHAR NOT NULL,
    eps_mean DOUBLE,
    eps_high DOUBLE,
    eps_low DOUBLE,
    revenue_mean DOUBLE,
    revenue_high DOUBLE,
    revenue_low DOUBLE,
    analyst_count INTEGER,
    eps_mean_7d_ago DOUBLE,
    eps_mean_30d_ago DOUBLE,
    eps_mean_90d_ago DOUBLE,
    revenue_mean_7d_ago DOUBLE,
    revenue_mean_30d_ago DOUBLE,
    revenue_mean_90d_ago DOUBLE,
    source VARCHAR NOT NULL,
    source_url VARCHAR,
    retrieved_at TIMESTAMP NOT NULL,
    as_of_date DATE NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS guidance_snapshots_id_seq;
CREATE TABLE IF NOT EXISTS guidance_snapshots (
    id BIGINT PRIMARY KEY DEFAULT nextval('guidance_snapshots_id_seq'),
    ticker VARCHAR NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,
    revenue_low DOUBLE,
    revenue_high DOUBLE,
    margin_guidance DOUBLE,
    capex_guidance DOUBLE,
    fiscal_period VARCHAR,
    guidance_scope VARCHAR,
    currency VARCHAR,
    value_unit VARCHAR,
    source_filing VARCHAR NOT NULL,
    source_date DATE NOT NULL,
    retrieved_at TIMESTAMP NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS investment_analysis_id_seq;
CREATE TABLE IF NOT EXISTS investment_analysis (
    id BIGINT PRIMARY KEY DEFAULT nextval('investment_analysis_id_seq'),
    ticker VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    price DOUBLE NOT NULL,
    decision VARCHAR NOT NULL,
    confidence DOUBLE NOT NULL,
    expected_return DOUBLE NOT NULL,
    expected_return_horizon_months INTEGER,
    expected_return_method VARCHAR,
    expected_return_annualized DOUBLE,
    expected_return_basis VARCHAR,
    bull_value DOUBLE,
    base_value DOUBLE,
    bear_value DOUBLE,
    thesis_json VARCHAR NOT NULL,
    variant_perception_json VARCHAR NOT NULL,
    invalidation_json VARCHAR NOT NULL,
    run_id VARCHAR,
    model_name VARCHAR,
    model_version VARCHAR,
    prompt_version VARCHAR,
    input_snapshot_json VARCHAR,
    assumptions_json VARCHAR
);

CREATE SEQUENCE IF NOT EXISTS catalysts_id_seq;
CREATE TABLE IF NOT EXISTS catalysts (
    id BIGINT PRIMARY KEY DEFAULT nextval('catalysts_id_seq'),
    ticker VARCHAR NOT NULL,
    event_date DATE NOT NULL,
    event_type VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    importance VARCHAR NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS macro_snapshots_id_seq;
CREATE TABLE IF NOT EXISTS macro_snapshots (
    id BIGINT PRIMARY KEY DEFAULT nextval('macro_snapshots_id_seq'),
    indicator VARCHAR NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,
    observation_date DATE NOT NULL,
    value DOUBLE NOT NULL,
    unit VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    transformation VARCHAR NOT NULL,
    reference_date DATE,
    reference_value DOUBLE,
    percentile_5y DOUBLE,
    source VARCHAR NOT NULL,
    source_url VARCHAR,
    retrieved_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS macro_snapshots_indicator_snapshot_idx
    ON macro_snapshots (indicator, snapshot_at);
