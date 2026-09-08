-- MedInsure dimension ETL (Deliverable 3)
-- Prerequisites: 00_schemas.sql, 01_oltp.sql, 02_dw_ddl.sql
-- Run: psql -h localhost -p 5432 -U postgres -d medinsure -f sql/03_etl_dims.sql
-- Order: dim_date → Type 1 dims → SCD2 initial history → SCD2 incremental → hard SCD one-current gate

\timing on
SET client_min_messages TO WARNING;
SET synchronous_commit TO OFF;
SET work_mem TO '256MB';

-- ===========================================================================
-- 1) dim_date — calendar 2020-01-01 .. 2030-12-31 (pure SQL)
-- ===========================================================================
INSERT INTO dw.dim_date (
    date_key, full_date, year, quarter, month, month_name,
    day_of_month, day_of_week, day_name, is_weekend
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::int,
    d::date,
    EXTRACT(YEAR FROM d)::int,
    EXTRACT(QUARTER FROM d)::int,
    EXTRACT(MONTH FROM d)::int,
    TO_CHAR(d, 'FMMonth'),
    EXTRACT(DAY FROM d)::int,
    EXTRACT(ISODOW FROM d)::int,
    TO_CHAR(d, 'FMDay'),
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series(DATE '2020-01-01', DATE '2030-12-31', INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

SELECT COUNT(*) AS dim_date_rows,
       MIN(full_date) AS min_date,
       MAX(full_date) AS max_date
FROM dw.dim_date;

-- ===========================================================================
-- 2) Type 1 dimensions — UPSERT (preserve key = 0 NA rows)
-- ===========================================================================
INSERT INTO dw.dim_plan (plan_id, plan_code, plan_name, plan_type, deductible, oop_max)
SELECT plan_id, plan_code, plan_name, plan_type, deductible, oop_max
FROM public.plan_types
ON CONFLICT (plan_id) DO UPDATE
SET plan_code  = EXCLUDED.plan_code,
    plan_name  = EXCLUDED.plan_name,
    plan_type  = EXCLUDED.plan_type,
    deductible = EXCLUDED.deductible,
    oop_max    = EXCLUDED.oop_max;

INSERT INTO dw.dim_diagnosis (diagnosis_code, description, category)
SELECT diagnosis_code, description, category
FROM public.diagnosis_codes
ON CONFLICT (diagnosis_code) DO UPDATE
SET description = EXCLUDED.description,
    category    = EXCLUDED.category;

INSERT INTO dw.dim_procedure (procedure_code, description, category)
SELECT procedure_code, description, category
FROM public.procedure_codes
ON CONFLICT (procedure_code) DO UPDATE
SET description = EXCLUDED.description,
    category    = EXCLUDED.category;

SELECT
    (SELECT COUNT(*) FROM dw.dim_plan WHERE plan_key <> 0) AS plans,
    (SELECT COUNT(*) FROM dw.dim_diagnosis WHERE diagnosis_key <> 0) AS diagnoses,
    (SELECT COUNT(*) FROM dw.dim_procedure WHERE procedure_key <> 0) AS procedures;

-- ===========================================================================
-- 3) dim_member SCD Type 2 — initial load from member_plan_history
--    (real multi-version rows; inclusive effective_end)
-- ===========================================================================
-- Idempotent: only seed history when no real members exist yet
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dw.dim_member WHERE member_key <> 0 LIMIT 1) THEN
        INSERT INTO dw.dim_member (
            member_id, first_name, last_name, date_of_birth, gender,
            enrollment_date, plan_id, state, zip_code,
            effective_start, effective_end, is_current
        )
        SELECT
            m.member_id,
            m.first_name,
            m.last_name,
            m.date_of_birth,
            m.gender,
            m.enrollment_date,
            h.plan_id,
            h.state,
            h.zip_code,
            h.effective_start,
            h.effective_end,
            (h.effective_end = DATE '9999-12-31')
        FROM public.member_plan_history h
        JOIN public.members m ON m.member_id = h.member_id
        ORDER BY h.member_id, h.effective_start;
    END IF;
END $$;

SELECT COUNT(*) AS member_versions,
       COUNT(*) FILTER (WHERE is_current) AS member_current,
       COUNT(DISTINCT member_id) FILTER (WHERE member_key <> 0) AS distinct_members
FROM dw.dim_member
WHERE member_key <> 0;

-- ===========================================================================
-- 4) dim_member SCD Type 2 — incremental close-then-insert
--    Tracked attrs: plan_id, state, zip_code (IS DISTINCT FROM)
-- ===========================================================================
BEGIN;

WITH changed AS (
    SELECT s.member_id
    FROM public.members s
    JOIN dw.dim_member d
      ON d.member_id = s.member_id
     AND d.is_current
     AND d.member_key <> 0
    WHERE s.plan_id  IS DISTINCT FROM d.plan_id
       OR s.state    IS DISTINCT FROM d.state
       OR s.zip_code IS DISTINCT FROM d.zip_code
)
UPDATE dw.dim_member d
SET effective_end = CURRENT_DATE - 1,   -- inclusive: old version ends yesterday
    is_current    = FALSE
FROM changed c
WHERE d.member_id = c.member_id
  AND d.is_current
  AND d.member_key <> 0
  AND d.effective_start <= CURRENT_DATE - 1;  -- avoid invalid ranges if same-day re-run

INSERT INTO dw.dim_member (
    member_id, first_name, last_name, date_of_birth, gender,
    enrollment_date, plan_id, state, zip_code,
    effective_start, effective_end, is_current
)
SELECT
    s.member_id,
    s.first_name,
    s.last_name,
    s.date_of_birth,
    s.gender,
    s.enrollment_date,
    s.plan_id,
    s.state,
    s.zip_code,
    CURRENT_DATE,
    DATE '9999-12-31',
    TRUE
FROM public.members s
LEFT JOIN dw.dim_member d
       ON d.member_id = s.member_id
      AND d.is_current
      AND d.member_key <> 0
WHERE d.member_key IS NULL;

COMMIT;

-- ===========================================================================
-- 5) dim_provider SCD Type 2 — initial load from provider_network_history
-- ===========================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dw.dim_provider WHERE provider_key <> 0 LIMIT 1) THEN
        INSERT INTO dw.dim_provider (
            provider_id, provider_name, provider_type, specialty,
            network_status, network_effective_date,
            effective_start, effective_end, is_current
        )
        SELECT
            p.provider_id,
            p.provider_name,
            p.provider_type,
            h.specialty,
            h.network_status,
            p.network_effective_date,
            h.effective_start,
            h.effective_end,
            (h.effective_end = DATE '9999-12-31')
        FROM public.provider_network_history h
        JOIN public.providers p ON p.provider_id = h.provider_id
        ORDER BY h.provider_id, h.effective_start;
    END IF;
END $$;

SELECT COUNT(*) AS provider_versions,
       COUNT(*) FILTER (WHERE is_current) AS provider_current,
       COUNT(DISTINCT provider_id) FILTER (WHERE provider_key <> 0) AS distinct_providers
FROM dw.dim_provider
WHERE provider_key <> 0;

-- ===========================================================================
-- 6) dim_provider SCD Type 2 — incremental close-then-insert
--    Tracked attrs: network_status, specialty
-- ===========================================================================
BEGIN;

WITH changed AS (
    SELECT s.provider_id
    FROM public.providers s
    JOIN dw.dim_provider d
      ON d.provider_id = s.provider_id
     AND d.is_current
     AND d.provider_key <> 0
    WHERE s.network_status IS DISTINCT FROM d.network_status
       OR s.specialty      IS DISTINCT FROM d.specialty
)
UPDATE dw.dim_provider d
SET effective_end = CURRENT_DATE - 1,
    is_current    = FALSE
FROM changed c
WHERE d.provider_id = c.provider_id
  AND d.is_current
  AND d.provider_key <> 0
  AND d.effective_start <= CURRENT_DATE - 1;

INSERT INTO dw.dim_provider (
    provider_id, provider_name, provider_type, specialty,
    network_status, network_effective_date,
    effective_start, effective_end, is_current
)
SELECT
    s.provider_id,
    s.provider_name,
    s.provider_type,
    s.specialty,
    s.network_status,
    s.network_effective_date,
    CURRENT_DATE,
    DATE '9999-12-31',
    TRUE
FROM public.providers s
LEFT JOIN dw.dim_provider d
       ON d.provider_id = s.provider_id
      AND d.is_current
      AND d.provider_key <> 0
WHERE d.provider_key IS NULL;

COMMIT;

-- ===========================================================================
-- 7) Hard gate — no natural key may have >1 is_current = TRUE
--    Log violators to etl.*, then RAISE so the job fails (ON_ERROR_STOP).
--    Inserts run as separate autocommit statements so logs survive the exception.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS etl.scd_current_violations (
    violation_id   BIGSERIAL PRIMARY KEY,
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    dimension_name TEXT NOT NULL,              -- dim_member | dim_provider
    natural_key    INT NOT NULL,               -- member_id / provider_id
    current_count  INT NOT NULL,
    details        JSONB
);

CREATE TABLE IF NOT EXISTS etl.job_failures (
    failure_id   BIGSERIAL PRIMARY KEY,
    failed_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    step_name    TEXT NOT NULL,
    error_code   TEXT NOT NULL,
    message      TEXT NOT NULL,
    details      JSONB
);

CREATE TABLE IF NOT EXISTS dw.etl_run_log (
    run_id        BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    table_name    TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    rows_read     BIGINT,
    rows_loaded   BIGINT,
    rows_rejected BIGINT,
    status        TEXT NOT NULL DEFAULT 'running'
);

DROP TABLE IF EXISTS tmp_scd_violators;
CREATE TEMP TABLE tmp_scd_violators AS
SELECT
    'dim_member'::text AS dimension_name,
    member_id          AS natural_key,
    COUNT(*)::int      AS current_count,
    jsonb_build_object(
        'member_keys', jsonb_agg(member_key ORDER BY member_key)
    ) AS details
FROM dw.dim_member
WHERE is_current
  AND member_key <> 0
GROUP BY member_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'dim_provider'::text,
    provider_id,
    COUNT(*)::int,
    jsonb_build_object(
        'provider_keys', jsonb_agg(provider_key ORDER BY provider_key)
    )
FROM dw.dim_provider
WHERE is_current
  AND provider_key <> 0
GROUP BY provider_id
HAVING COUNT(*) > 1;

-- Persist per-key violators (survives later RAISE under psql autocommit)
INSERT INTO etl.scd_current_violations (
    dimension_name, natural_key, current_count, details
)
SELECT dimension_name, natural_key, current_count, details
FROM tmp_scd_violators;

INSERT INTO dw.etl_run_log (
    table_name, started_at, finished_at, rows_read, rows_loaded, rows_rejected, status
)
SELECT
    'validate_scd_one_current',
    clock_timestamp(),
    clock_timestamp(),
    (SELECT COUNT(*) FROM tmp_scd_violators),
    0,
    (SELECT COUNT(*) FROM tmp_scd_violators),
    CASE WHEN EXISTS (SELECT 1 FROM tmp_scd_violators) THEN 'failed' ELSE 'success' END;

-- Job-level failure row only when the gate trips (committed before RAISE)
INSERT INTO etl.job_failures (step_name, error_code, message, details)
SELECT
    'validate_scd_one_current',
    'multiple_is_current',
    format(
        'SCD one-current violated: %s member natural key(s), %s provider natural key(s)',
        (SELECT COUNT(*) FROM tmp_scd_violators WHERE dimension_name = 'dim_member'),
        (SELECT COUNT(*) FROM tmp_scd_violators WHERE dimension_name = 'dim_provider')
    ),
    jsonb_build_object(
        'member_violators',
            (SELECT COUNT(*) FROM tmp_scd_violators WHERE dimension_name = 'dim_member'),
        'provider_violators',
            (SELECT COUNT(*) FROM tmp_scd_violators WHERE dimension_name = 'dim_provider'),
        'sample',
            COALESCE(
                (SELECT jsonb_agg(jsonb_build_object(
                    'dimension', dimension_name,
                    'natural_key', natural_key,
                    'current_count', current_count
                )) FROM (
                    SELECT * FROM tmp_scd_violators LIMIT 20
                ) s),
                '[]'::jsonb
            )
    )
WHERE EXISTS (SELECT 1 FROM tmp_scd_violators);

SELECT
    dimension_name,
    COUNT(*) AS violator_keys,
    SUM(current_count) AS current_rows_involved
FROM tmp_scd_violators
GROUP BY dimension_name
ORDER BY 1;

-- Fail the script when any violator exists (logs above already committed)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM tmp_scd_violators) THEN
        RAISE EXCEPTION
            'SCD one-current check failed — see etl.scd_current_violations and etl.job_failures (step validate_scd_one_current)';
    END IF;
END $$;

SELECT 'validate_scd_one_current' AS check_name, 'PASS' AS status;

-- Optional demo: force one member change, then re-run section 4 alone to see a new version.
-- UPDATE public.members SET state = 'WA', zip_code = '98101' WHERE member_id = 1;
