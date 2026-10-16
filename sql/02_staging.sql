-- 02_staging.sql
-- Staging layer: typed, cleaned, validated rows prepared for core upsert

CREATE TABLE IF NOT EXISTS staging.students (
    student_id TEXT NOT NULL,
    department TEXT NOT NULL,
    graduation_year INT NOT NULL,
    cgpa NUMERIC(3,2),
    row_hash TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_row_number INT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.companies (
    company_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    company_name_raw TEXT,
    sector TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_row_number INT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.applications (
    application_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    applied_at DATE NOT NULL,
    status TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_row_number INT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.offers (
    offer_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    compensation_lpa NUMERIC(6,2) NOT NULL,
    offer_date DATE NOT NULL,
    row_hash TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_row_number INT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staging_students_batch ON staging.students(batch_id);
CREATE INDEX IF NOT EXISTS idx_staging_companies_batch ON staging.companies(batch_id);
CREATE INDEX IF NOT EXISTS idx_staging_applications_batch ON staging.applications(batch_id);
CREATE INDEX IF NOT EXISTS idx_staging_offers_batch ON staging.offers(batch_id);

