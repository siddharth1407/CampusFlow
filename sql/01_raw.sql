-- 01_raw.sql
-- Ingestion landing tables: stores incoming data as raw TEXT with lineage metadata

CREATE TABLE IF NOT EXISTS raw.students (
    raw_id BIGSERIAL PRIMARY KEY,
    student_id TEXT,
    department TEXT,
    graduation_year TEXT,
    cgpa TEXT,
    batch_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.companies (
    raw_id BIGSERIAL PRIMARY KEY,
    company_id TEXT,
    company_name TEXT,
    sector TEXT,
    batch_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.applications (
    raw_id BIGSERIAL PRIMARY KEY,
    application_id TEXT,
    student_id TEXT,
    company_id TEXT,
    applied_at TEXT,
    status TEXT,
    batch_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.offers (
    raw_id BIGSERIAL PRIMARY KEY,
    offer_id TEXT,
    student_id TEXT,
    company_id TEXT,
    compensation_lpa TEXT,
    offer_date TEXT,
    batch_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_students_batch ON raw.students(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_companies_batch ON raw.companies(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_applications_batch ON raw.applications(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_offers_batch ON raw.offers(batch_id);

