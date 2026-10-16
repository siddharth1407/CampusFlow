-- 06_analytics_views.sql
-- Reporting views built on top of core and ops schemas

-- 1. Overall placement rate by graduation year
CREATE OR REPLACE VIEW analytics.placement_summary AS
SELECT
    s.graduation_year,
    COUNT(DISTINCT s.student_id) AS total_students,
    COUNT(DISTINCT o.student_id) AS placed_students,
    ROUND(
        COUNT(DISTINCT o.student_id)::NUMERIC / NULLIF(COUNT(DISTINCT s.student_id), 0) * 100.0,
        2
    ) AS placement_rate_pct
FROM core.students s
LEFT JOIN core.offers o ON s.student_id = o.student_id
GROUP BY s.graduation_year
ORDER BY s.graduation_year DESC;

-- 2. Offers, mean, and median compensation by department
CREATE OR REPLACE VIEW analytics.department_offers AS
SELECT
    s.department,
    COUNT(o.offer_id) AS total_offers,
    COUNT(DISTINCT o.student_id) AS students_placed,
    ROUND(AVG(o.compensation_lpa), 2) AS mean_compensation_lpa,
    ROUND(
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.compensation_lpa)::NUMERIC,
        2
    ) AS median_compensation_lpa,
    MIN(o.compensation_lpa) AS min_compensation_lpa,
    MAX(o.compensation_lpa) AS max_compensation_lpa
FROM core.students s
LEFT JOIN core.offers o ON s.student_id = o.student_id
GROUP BY s.department
ORDER BY total_offers DESC;

-- 3. Company recruitment funnel and conversion rates
CREATE OR REPLACE VIEW analytics.company_funnel AS
SELECT
    c.company_id,
    c.company_name,
    c.sector,
    COUNT(a.application_id) AS total_applications,
    COUNT(CASE WHEN a.status IN ('shortlisted', 'interviewed', 'offered') THEN 1 END) AS total_shortlisted,
    COUNT(CASE WHEN a.status IN ('interviewed', 'offered') THEN 1 END) AS total_interviewed,
    COUNT(CASE WHEN a.status = 'offered' THEN 1 END) AS total_offered,
    ROUND(
        COUNT(CASE WHEN a.status = 'offered' THEN 1 END)::NUMERIC /
        NULLIF(COUNT(a.application_id), 0) * 100.0,
        2
    ) AS conversion_rate_pct
FROM core.companies c
LEFT JOIN core.applications a ON c.company_id = a.company_id
GROUP BY c.company_id, c.company_name, c.sector
ORDER BY total_applications DESC;

-- 4. Sector trends by month
CREATE OR REPLACE VIEW analytics.sector_trends AS
SELECT
    c.sector,
    TO_CHAR(DATE_TRUNC('month', o.offer_date), 'YYYY-MM') AS offer_month,
    COUNT(o.offer_id) AS total_offers,
    ROUND(AVG(o.compensation_lpa), 2) AS mean_compensation_lpa,
    ROUND(
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.compensation_lpa)::NUMERIC,
        2
    ) AS median_compensation_lpa
FROM core.offers o
JOIN core.companies c ON o.company_id = c.company_id
GROUP BY c.sector, DATE_TRUNC('month', o.offer_date)
ORDER BY offer_month DESC, total_offers DESC;

-- 5. Pipeline health and quarantine breakdown
CREATE OR REPLACE VIEW analytics.pipeline_health AS
SELECT
    r.run_id,
    r.batch_id,
    r.started_at,
    r.status AS run_status,
    r.rows_read,
    r.rows_loaded_new,
    r.rows_updated,
    r.rows_unchanged,
    r.rows_rejected,
    rej.source_table,
    rej.reason_code,
    COUNT(rej.id) AS rejects_for_reason
FROM ops.pipeline_runs r
LEFT JOIN ops.rejected_records rej ON r.run_id = rej.run_id
GROUP BY
    r.run_id,
    r.batch_id,
    r.started_at,
    r.status,
    r.rows_read,
    r.rows_loaded_new,
    r.rows_updated,
    r.rows_unchanged,
    r.rows_rejected,
    rej.source_table,
    rej.reason_code
ORDER BY r.started_at DESC, rejects_for_reason DESC;

