-- sql/analytics.sql
-- 10 Analytical Queries required by the CampusFlow Specification (Section 8.2)

-- 1. How many students received at least one offer, and what is the placement rate by department?
SELECT
    s.department,
    COUNT(DISTINCT s.student_id) AS total_students,
    COUNT(DISTINCT o.student_id) AS placed_students,
    ROUND(
        COUNT(DISTINCT o.student_id)::NUMERIC / NULLIF(COUNT(DISTINCT s.student_id), 0) * 100.0,
        2
    ) AS placement_rate_pct
FROM core.students s
LEFT JOIN core.offers o ON s.student_id = o.student_id
GROUP BY s.department
ORDER BY placement_rate_pct DESC, total_students DESC;

-- 2. Which companies received the most applications (top 10)?
SELECT
    c.company_name,
    c.sector,
    COUNT(a.application_id) AS total_applications
FROM core.companies c
JOIN core.applications a ON c.company_id = a.company_id
GROUP BY c.company_name, c.sector
ORDER BY total_applications DESC
LIMIT 10;

-- 3. Offer conversion rate by company and by sector.
SELECT
    c.sector,
    c.company_name,
    COUNT(a.application_id) AS total_applications,
    COUNT(CASE WHEN a.status = 'offered' THEN 1 END) AS total_offers,
    ROUND(
        COUNT(CASE WHEN a.status = 'offered' THEN 1 END)::NUMERIC /
        NULLIF(COUNT(a.application_id), 0) * 100.0,
        2
    ) AS conversion_rate_pct
FROM core.companies c
LEFT JOIN core.applications a ON c.company_id = a.company_id
GROUP BY c.sector, c.company_name
HAVING COUNT(a.application_id) > 0
ORDER BY c.sector, conversion_rate_pct DESC;

-- 4. Median and average compensation by department (percentile_cont(0.5)).
SELECT
    s.department,
    COUNT(o.offer_id) AS offers_count,
    ROUND(AVG(o.compensation_lpa), 2) AS avg_compensation_lpa,
    ROUND(
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.compensation_lpa)::NUMERIC,
        2
    ) AS median_compensation_lpa,
    MIN(o.compensation_lpa) AS min_compensation_lpa,
    MAX(o.compensation_lpa) AS max_compensation_lpa
FROM core.students s
JOIN core.offers o ON s.student_id = o.student_id
GROUP BY s.department
ORDER BY median_compensation_lpa DESC;

-- 5. Top 3 companies per sector by offers (window function: ROW_NUMBER() OVER (PARTITION BY ...)).
WITH sector_company_offers AS (
    SELECT
        c.sector,
        c.company_name,
        COUNT(o.offer_id) AS total_offers,
        ROW_NUMBER() OVER (
            PARTITION BY c.sector
            ORDER BY COUNT(o.offer_id) DESC, c.company_name ASC
        ) AS rank_in_sector
    FROM core.companies c
    JOIN core.offers o ON c.company_id = o.company_id
    GROUP BY c.sector, c.company_name
)
SELECT
    sector,
    company_name,
    total_offers,
    rank_in_sector
FROM sector_company_offers
WHERE rank_in_sector <= 3
ORDER BY sector, rank_in_sector;

-- 6. Monthly offer trend with month-over-month change (LAG).
WITH monthly_offers AS (
    SELECT
        TO_CHAR(DATE_TRUNC('month', offer_date), 'YYYY-MM') AS offer_month,
        COUNT(offer_id) AS total_offers,
        ROUND(AVG(compensation_lpa), 2) AS avg_compensation_lpa
    FROM core.offers
    GROUP BY DATE_TRUNC('month', offer_date)
)
SELECT
    offer_month,
    total_offers,
    LAG(total_offers, 1) OVER (ORDER BY offer_month) AS prev_month_offers,
    total_offers - LAG(total_offers, 1) OVER (ORDER BY offer_month) AS mom_offer_diff,
    ROUND(
        (total_offers - LAG(total_offers, 1) OVER (ORDER BY offer_month))::NUMERIC /
        NULLIF(LAG(total_offers, 1) OVER (ORDER BY offer_month), 0) * 100.0,
        2
    ) AS mom_growth_pct,
    avg_compensation_lpa
FROM monthly_offers
ORDER BY offer_month;

-- 7. Students with multiple offers and their highest offer (CTE + window function).
WITH student_offer_ranks AS (
    SELECT
        o.student_id,
        s.department,
        o.offer_id,
        c.company_name,
        o.compensation_lpa,
        o.offer_date,
        COUNT(o.offer_id) OVER (PARTITION BY o.student_id) AS total_offers_received,
        ROW_NUMBER() OVER (
            PARTITION BY o.student_id
            ORDER BY o.compensation_lpa DESC, o.offer_date DESC
        ) AS offer_rank
    FROM core.offers o
    JOIN core.students s ON o.student_id = s.student_id
    JOIN core.companies c ON o.company_id = c.company_id
)
SELECT
    student_id,
    department,
    total_offers_received,
    company_name AS highest_paying_company,
    compensation_lpa AS highest_compensation_lpa,
    offer_date
FROM student_offer_ranks
WHERE total_offers_received > 1 AND offer_rank = 1
ORDER BY highest_compensation_lpa DESC;

-- 8. Rejected records by reason code per pipeline run.
SELECT
    r.batch_id,
    r.run_id,
    r.started_at,
    rej.source_table,
    rej.reason_code,
    COUNT(rej.id) AS reject_count
FROM ops.pipeline_runs r
JOIN ops.rejected_records rej ON r.run_id = rej.run_id
GROUP BY r.batch_id, r.run_id, r.started_at, rej.source_table, rej.reason_code
ORDER BY r.started_at DESC, reject_count DESC;

-- 9. Data quality trend: reject rate across batches.
SELECT
    r.batch_id,
    r.run_id,
    r.started_at,
    r.rows_read,
    r.rows_loaded_new,
    r.rows_updated,
    r.rows_rejected,
    ROUND(
        r.rows_rejected::NUMERIC / NULLIF(r.rows_read, 0) * 100.0,
        2
    ) AS reject_rate_pct
FROM ops.pipeline_runs r
ORDER BY r.started_at ASC;

-- 10. Applications stuck at a stage for more than N days (date logic).
-- (e.g., status is 'applied' or 'shortlisted' and more than 30 days elapsed since application date)
SELECT
    a.application_id,
    a.student_id,
    s.department,
    c.company_name,
    a.status,
    a.applied_at,
    CURRENT_DATE - a.applied_at AS days_elapsed
FROM core.applications a
JOIN core.students s ON a.student_id = s.student_id
JOIN core.companies c ON a.company_id = c.company_id
WHERE a.status IN ('applied', 'shortlisted')
  AND (CURRENT_DATE - a.applied_at) > 30
ORDER BY days_elapsed DESC;

