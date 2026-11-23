-- CloudHR control totals for year Y = 2025, the latest full calendar year.
-- December of Y is the snapshot dated 2025-12-01 (the first of the month).
-- Run inside the container:
--   psql -U postgres -d cloudhr -f /sql/controls.sql
-- Organisation 1 is the first check. Each query also returns the whole database.
\set ON_ERROR_STOP on

-- Active headcount: one month only. Not a sum across months.
SELECT 'December active headcount' AS metric,
       COUNT(*) FILTER (WHERE org_id = 1) AS org_1,
       COUNT(*) AS whole_database
FROM hr.employee_monthly_snapshots
WHERE snapshot_month = DATE '2025-12-01'
  AND is_active;

-- Q1 headcount is the March snapshot.
SELECT 'Q1 headcount, March snapshot' AS metric,
       COUNT(*) FILTER (WHERE org_id = 1 AND snapshot_month = DATE '2025-03-01') AS org_1,
       COUNT(*) FILTER (WHERE snapshot_month = DATE '2025-03-01') AS whole_database
FROM hr.employee_monthly_snapshots
WHERE is_active
  AND snapshot_month IN (DATE '2025-01-01', DATE '2025-02-01', DATE '2025-03-01');

-- The incorrect alternative: adding the three month-end snapshots.
SELECT 'Q1 headcount, Jan+Feb+Mar sum' AS metric,
       COUNT(*) FILTER (WHERE org_id = 1) AS org_1,
       COUNT(*) AS whole_database
FROM hr.employee_monthly_snapshots
WHERE is_active
  AND snapshot_month IN (DATE '2025-01-01', DATE '2025-02-01', DATE '2025-03-01');

-- Hires: hire_date inside 2025, including planted dates that fall after termination.
SELECT 'Hires in 2025' AS metric,
       COUNT(*) FILTER (WHERE org_id = 1) AS org_1,
       COUNT(*) AS whole_database
FROM hr.employees
WHERE hire_date >= DATE '2025-01-01'
  AND hire_date < DATE '2026-01-01';

-- Terminations inside 2025. Voluntary is that reason; every other reason is other.
SELECT 'Terminations in 2025' AS metric,
       COUNT(*) FILTER (WHERE org_id = 1 AND termination_reason = 'Voluntary') AS org_1_voluntary,
       COUNT(*) FILTER (WHERE org_id = 1 AND termination_reason IS DISTINCT FROM 'Voluntary') AS org_1_other,
       COUNT(*) FILTER (WHERE termination_reason = 'Voluntary') AS all_voluntary,
       COUNT(*) FILTER (WHERE termination_reason IS DISTINCT FROM 'Voluntary') AS all_other
FROM hr.employees
WHERE termination_date >= DATE '2025-01-01'
  AND termination_date < DATE '2026-01-01';

-- December average salary. Nulls and non-positive values are excluded.
SELECT 'December average salary' AS metric,
       COUNT(*) FILTER (WHERE org_id = 1) AS org_1_rows,
       AVG(base_salary_usd) FILTER (WHERE org_id = 1) AS org_1_avg,
       COUNT(*) AS all_rows,
       AVG(base_salary_usd) AS all_avg
FROM hr.employee_monthly_snapshots
WHERE snapshot_month = DATE '2025-12-01'
  AND base_salary_usd IS NOT NULL
  AND base_salary_usd > 0;

-- Leave days in 2025 by type. A leave counts in the year of its start_date.
SELECT COALESCE(leave_type, 'Total') AS leave_type,
       COALESCE(SUM(days_taken) FILTER (WHERE org_id = 1), 0) AS org_1_days,
       COALESCE(SUM(days_taken), 0) AS whole_database_days
FROM hr.leave_records
WHERE start_date >= DATE '2025-01-01'
  AND start_date < DATE '2026-01-01'
GROUP BY ROLLUP (leave_type)
ORDER BY GROUPING (leave_type), leave_type;
