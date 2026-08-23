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
    source VARCHAR NOT NULL,
    source_url VARCHAR,
    retrieved_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS macro_snapshots_indicator_snapshot_idx
    ON macro_snapshots (indicator, snapshot_at);
