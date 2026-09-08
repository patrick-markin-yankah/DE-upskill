-- MedInsure data quality checks (Deliverable 6)
-- Run: psql -h localhost -p 5432 -U postgres -d medinsure -f sql/07_quality.sql
-- PASS when pass_rate >= 99%. Output: check_name, rows_evaluated, passed, failed, pass_rate, status.

\timing on
SET client_min_messages TO WARNING;

CREATE TABLE IF NOT EXISTS etl.quality_report (
    run_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    check_name      TEXT NOT NULL,
    rows_evaluated  BIGINT NOT NULL,
    passed          BIGINT NOT NULL,
    failed          BIGINT NOT NULL,
    pass_rate       NUMERIC(6,2) NOT NULL,
    status          TEXT NOT NULL
);

-- Keep latest run only for a clean report table (history optional later)
TRUNCATE etl.quality_report;

WITH
-- ---------------------------------------------------------------------------
-- 1) fact_claim: every claim has valid service/processed date, member, provider
-- ---------------------------------------------------------------------------
fc_keys AS (
    SELECT
        f.claim_key,
        CASE
            WHEN ds.date_key IS NULL
              OR dp_dt.date_key IS NULL
              OR m.member_key IS NULL
              OR p.provider_key IS NULL
              OR f.member_key = 0
              OR f.provider_key = 0
            THEN 1 ELSE 0
        END AS is_fail
    FROM dw.fact_claim f
    LEFT JOIN dw.dim_date ds     ON ds.date_key = f.service_date_key
    LEFT JOIN dw.dim_date dp_dt  ON dp_dt.date_key = f.processed_date_key
    LEFT JOIN dw.dim_member m    ON m.member_key = f.member_key
    LEFT JOIN dw.dim_provider p  ON p.provider_key = f.provider_key
),
c1 AS (
    SELECT
        'fact_claim.valid_date_member_provider_keys' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) - SUM(is_fail) AS passed,
        SUM(is_fail) AS failed
    FROM fc_keys
),

-- ---------------------------------------------------------------------------
-- 2) fact_claim: paid not > allowed * 1.05
-- ---------------------------------------------------------------------------
c2 AS (
    SELECT
        'fact_claim.paid_vs_allowed_5pct' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) FILTER (WHERE NOT (total_paid > total_allowed * 1.05)) AS passed,
        COUNT(*) FILTER (WHERE total_paid > total_allowed * 1.05) AS failed
    FROM dw.fact_claim
),

-- ---------------------------------------------------------------------------
-- 3) dim_member: at most one is_current per member_id
-- ---------------------------------------------------------------------------
c3 AS (
    SELECT
        'dim_member.one_current_per_id' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) FILTER (WHERE current_cnt = 1) AS passed,
        COUNT(*) FILTER (WHERE current_cnt > 1) AS failed
    FROM (
        SELECT member_id, COUNT(*) AS current_cnt
        FROM dw.dim_member
        WHERE is_current AND member_key <> 0
        GROUP BY member_id
    ) x
),

-- ---------------------------------------------------------------------------
-- 4) dim_provider: at most one is_current per provider_id
-- ---------------------------------------------------------------------------
c4 AS (
    SELECT
        'dim_provider.one_current_per_id' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) FILTER (WHERE current_cnt = 1) AS passed,
        COUNT(*) FILTER (WHERE current_cnt > 1) AS failed
    FROM (
        SELECT provider_id, COUNT(*) AS current_cnt
        FROM dw.dim_provider
        WHERE is_current AND provider_key <> 0
        GROUP BY provider_id
    ) x
),

-- ---------------------------------------------------------------------------
-- 5) RI: every fact_claim_line.claim_id exists in fact_claim
-- ---------------------------------------------------------------------------
c5 AS (
    SELECT
        'fact_claim_line.claim_id_in_fact_claim' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) FILTER (WHERE fc.claim_id IS NOT NULL) AS passed,
        COUNT(*) FILTER (WHERE fc.claim_id IS NULL) AS failed
    FROM dw.fact_claim_line fl
    LEFT JOIN dw.fact_claim fc ON fc.claim_id = fl.claim_id
),

-- ---------------------------------------------------------------------------
-- 6) Orphaned procedure codes (line points at NA / missing real procedure)
-- ---------------------------------------------------------------------------
c6 AS (
    SELECT
        'fact_claim_line.procedure_in_dim_procedure' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) FILTER (
            WHERE fl.procedure_key <> 0
              AND dpr.procedure_key IS NOT NULL
              AND dpr.procedure_code <> 'N/A'
        ) AS passed,
        COUNT(*) FILTER (
            WHERE fl.procedure_key = 0
               OR dpr.procedure_key IS NULL
               OR dpr.procedure_code = 'N/A'
        ) AS failed
    FROM dw.fact_claim_line fl
    LEFT JOIN dw.dim_procedure dpr ON dpr.procedure_key = fl.procedure_key
),

-- ---------------------------------------------------------------------------
-- 7) Anachronistic claims: service_date < provider.network_effective_date
-- ---------------------------------------------------------------------------
c7 AS (
    SELECT
        'fact_claim.service_before_provider_network_effective' AS check_name,
        COUNT(*) AS rows_evaluated,
        COUNT(*) FILTER (WHERE NOT (d.full_date < p.network_effective_date)) AS passed,
        COUNT(*) FILTER (WHERE d.full_date < p.network_effective_date) AS failed
    FROM dw.fact_claim f
    JOIN dw.dim_provider p ON p.provider_key = f.provider_key
    JOIN dw.dim_date d     ON d.date_key = f.service_date_key
    WHERE p.provider_key <> 0
),

all_checks AS (
    SELECT * FROM c1
    UNION ALL SELECT * FROM c2
    UNION ALL SELECT * FROM c3
    UNION ALL SELECT * FROM c4
    UNION ALL SELECT * FROM c5
    UNION ALL SELECT * FROM c6
    UNION ALL SELECT * FROM c7
),
scored AS (
    SELECT
        check_name,
        rows_evaluated,
        passed,
        failed,
        ROUND(100.0 * passed / NULLIF(rows_evaluated, 0), 2) AS pass_rate,
        CASE
            WHEN rows_evaluated = 0 THEN 'FAIL'
            WHEN (100.0 * passed / rows_evaluated) >= 99.0 THEN 'PASS'
            ELSE 'FAIL'
        END AS status
    FROM all_checks
)
INSERT INTO etl.quality_report (check_name, rows_evaluated, passed, failed, pass_rate, status)
SELECT check_name, rows_evaluated, passed, failed, pass_rate, status
FROM scored
ORDER BY check_name;

-- Formatted report
SELECT
    check_name,
    rows_evaluated,
    passed,
    failed,
    pass_rate,
    status
FROM etl.quality_report
ORDER BY status DESC, pass_rate ASC, check_name;

-- Summary
SELECT
    COUNT(*) AS checks,
    COUNT(*) FILTER (WHERE status = 'PASS') AS passed_checks,
    COUNT(*) FILTER (WHERE status = 'FAIL') AS failed_checks
FROM etl.quality_report;
