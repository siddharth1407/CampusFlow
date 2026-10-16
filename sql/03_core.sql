-- 03_core.sql
-- Core business layer: trusted source of truth with constraints, foreign keys, and audit hashes

CREATE TABLE IF NOT EXISTS core.students (
    student_id TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    graduation_year INT NOT NULL,
    cgpa NUMERIC(3,2),
    row_hash TEXT NOT NULL,
    first_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_batch_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.companies (
    company_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    company_name_raw TEXT,
    sector TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    first_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_batch_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.applications (
    application_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES core.students(student_id),
    company_id TEXT NOT NULL REFERENCES core.companies(company_id),
    applied_at DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('applied', 'shortlisted', 'interviewed', 'offered', 'rejected', 'withdrawn')),
    row_hash TEXT NOT NULL,
    first_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_batch_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.offers (
    offer_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES core.students(student_id),
    company_id TEXT NOT NULL REFERENCES core.companies(company_id),
    compensation_lpa NUMERIC(6,2) NOT NULL CHECK (compensation_lpa > 0),
    offer_date DATE NOT NULL,
    row_hash TEXT NOT NULL,
    first_loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_batch_id TEXT NOT NULL
);

-- Performance & FK Indexes
CREATE INDEX IF NOT EXISTS idx_core_students_dept ON core.students(department);
CREATE INDEX IF NOT EXISTS idx_core_students_grad_year ON core.students(graduation_year);
CREATE INDEX IF NOT EXISTS idx_core_companies_sector ON core.companies(sector);
CREATE INDEX IF NOT EXISTS idx_core_applications_student ON core.applications(student_id);
CREATE INDEX IF NOT EXISTS idx_core_applications_company ON core.applications(company_id);
CREATE INDEX IF NOT EXISTS idx_core_applications_status ON core.applications(status);
CREATE INDEX IF NOT EXISTS idx_core_applications_applied_at ON core.applications(applied_at);
CREATE INDEX IF NOT EXISTS idx_core_offers_student ON core.offers(student_id);
CREATE INDEX IF NOT EXISTS idx_core_offers_company ON core.offers(company_id);
CREATE INDEX IF NOT EXISTS idx_core_offers_date ON core.offers(offer_date);

