ALTER TABLE guidance_snapshots ADD COLUMN IF NOT EXISTS fiscal_period VARCHAR;
ALTER TABLE guidance_snapshots ADD COLUMN IF NOT EXISTS guidance_scope VARCHAR;
ALTER TABLE guidance_snapshots ADD COLUMN IF NOT EXISTS currency VARCHAR;
ALTER TABLE guidance_snapshots ADD COLUMN IF NOT EXISTS value_unit VARCHAR;
