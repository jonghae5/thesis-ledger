CREATE TABLE IF NOT EXISTS evidence_bundles (
    bundle_id VARCHAR PRIMARY KEY,
    ticker VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    evidence_sha256 VARCHAR NOT NULL,
    evidence_json VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS evidence_bundles_ticker_created_idx
    ON evidence_bundles (ticker, created_at);

ALTER TABLE investment_analysis ADD COLUMN evidence_bundle_id VARCHAR;
