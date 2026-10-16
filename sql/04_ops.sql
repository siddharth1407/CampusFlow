-- 04_ops.sql
-- Operational audit, idempotency tracking, quarantine, and quality metrics

CREATE TABLE IF NOT EXISTS ops.file_ingestions (
    id BIGSERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    file_checksum TEXT NOT NULL,
    rows_in_file INT,
    status TEXT NOT NULL CHECK (status IN ('processed', 'skipped_duplicate', 'failed')),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_file_checksum UNIQUE (file_name, file_checksum)
);

CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_id UUID PRIMARY KEY,
    batch_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    rows_read INT DEFAULT 0,
    rows_loaded_new INT DEFAULT 0,
    rows_updated INT DEFAULT 0,
    rows_unchanged INT DEFAULT 0,
    rows_rejected INT DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS ops.rejected_records (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID REFERENCES ops.pipeline_runs(run_id) ON DELETE SET NULL,
    batch_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row_number INT,
    reason_code TEXT NOT NULL,
    reason_detail TEXT,
    raw_payload JSONB NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.quality_metrics (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID REFERENCES ops.pipeline_runs(run_id) ON DELETE SET NULL,
    table_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC(12,4) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Operational indexes
CREATE INDEX IF NOT EXISTS idx_ops_file_checksum ON ops.file_ingestions(file_name, file_checksum);
CREATE INDEX IF NOT EXISTS idx_ops_pipeline_batch ON ops.pipeline_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_ops_rejected_run ON ops.rejected_records(run_id);
CREATE INDEX IF NOT EXISTS idx_ops_rejected_reason ON ops.rejected_records(reason_code);
CREATE INDEX IF NOT EXISTS idx_ops_quality_run ON ops.quality_metrics(run_id);

