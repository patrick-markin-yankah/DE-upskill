-- MedInsure performance tuning (Deliverable 5)
-- Run: psql -h localhost -p 5432 -U postgres -d medinsure -f sql/06_tuning.sql
-- Captures EXPLAIN ANALYZE for analytics queries #1 and #6, adds a supporting
-- composite index, and creates mv_monthly_claims_summary for query #6.

\timing on
SET client_min_messages TO WARNING;

-- ===========================================================================
-- Additional supporting index for provider + date aggregations (Query #1, #8)
-- B-tree composite; INCLUDE total_paid enables index-only style aggregates
-- when the planner chooses an index scan.
-- ===========================================================================
CREATE INDEX IF NOT EXISTS idx_fact_claim_provider_service_paid
    ON dw.fact_claim (provider_key, service_date_key)
    INCLUDE (total_paid);

ANALYZE dw.fact_claim;
ANALYZE dw.dim_provider;
ANALYZE dw.dim_date;

-- ===========================================================================
-- EXPLAIN ANALYZE — Analytics Query #1 (top providers YoY)
-- ===========================================================================
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH annual_paid AS (
    SELECT
        p.provider_id,
        p.provider_name,
        p.specialty,
        d.year,
        SUM(f.total_paid) AS total_paid
    FROM dw.fact_claim f
    JOIN dw.dim_provider p ON p.provider_key = f.provider_key
    JOIN dw.dim_date d     ON d.date_key = f.service_date_key
    WHERE p.provider_key <> 0
    GROUP BY p.provider_id, p.provider_name, p.specialty, d.year
),
with_yoy AS (
    SELECT
        provider_id,
        provider_name,
        specialty,
        year,
        total_paid,
        LAG(total_paid) OVER (
            PARTITION BY provider_id
            ORDER BY year
        ) AS prior_year_paid
    FROM annual_paid
)
SELECT
    provider_id,
    provider_name,
    specialty,
    year,
    total_paid,
    prior_year_paid,
    ROUND(total_paid - COALESCE(prior_year_paid, 0), 2) AS yoy_change,
    ROUND(
        100.0 * (total_paid - prior_year_paid) / NULLIF(prior_year_paid, 0),
        1
    ) AS yoy_pct
FROM with_yoy
WHERE year = (SELECT MAX(year) FROM annual_paid)
ORDER BY total_paid DESC
LIMIT 20;

-- ===========================================================================
-- EXPLAIN ANALYZE — Analytics Query #6 (monthly volume + moving average)
-- BEFORE materialized view (base tables)
-- ===========================================================================
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        MAKE_DATE(d.year, d.month, 1) AS month_start,
        COUNT(*) AS claim_volume
    FROM dw.fact_claim f
    JOIN dw.dim_date d ON d.date_key = f.service_date_key
    GROUP BY d.year, d.month
)
SELECT
    year,
    month,
    month_start,
    claim_volume,
    ROUND(
        AVG(claim_volume) OVER (
            ORDER BY year, month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        1
    ) AS moving_avg_3mo
FROM monthly
ORDER BY year, month;

-- ===========================================================================
-- Materialized view — monthly claims summary (supports Query #6 dashboards)
-- ===========================================================================
DROP MATERIALIZED VIEW IF EXISTS dw.mv_monthly_claims_summary;

CREATE MATERIALIZED VIEW dw.mv_monthly_claims_summary AS
SELECT
    d.year,
    d.month,
    MAKE_DATE(d.year, d.month, 1) AS month_start,
    COUNT(*) AS claim_volume,
    SUM(f.total_paid) AS total_paid,
    SUM(f.total_allowed) AS total_allowed
FROM dw.fact_claim f
JOIN dw.dim_date d ON d.date_key = f.service_date_key
GROUP BY d.year, d.month;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_monthly_claims_summary
    ON dw.mv_monthly_claims_summary (year, month);

ANALYZE dw.mv_monthly_claims_summary;

-- Dashboard-style read from the MV (same moving-average logic)
SELECT
    year,
    month,
    month_start,
    claim_volume,
    ROUND(
        AVG(claim_volume) OVER (
            ORDER BY year, month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        1
    ) AS moving_avg_3mo
FROM dw.mv_monthly_claims_summary
ORDER BY year, month;

-- ===========================================================================
-- EXPLAIN ANALYZE — Query #6 AFTER materialized view
-- ===========================================================================
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    year,
    month,
    month_start,
    claim_volume,
    ROUND(
        AVG(claim_volume) OVER (
            ORDER BY year, month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        1
    ) AS moving_avg_3mo
FROM dw.mv_monthly_claims_summary
ORDER BY year, month;

-- Refresh recipe (run after nightly fact ETL):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY dw.mv_monthly_claims_summary;
-- CONCURRENTLY requires the unique index above and allows reads during refresh.

-- List fact indexes for the optimization report
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'dw'
  AND tablename IN ('fact_claim', 'fact_claim_line', 'mv_monthly_claims_summary')
ORDER BY tablename, indexname;
