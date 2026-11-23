-- CloudHR source database for the SK-06 capstone
-- Run inside the container:  psql -U postgres -d cloudhr -f /sql/01_create_and_load_cloudhr.sql
-- Safe to re-run: it drops and recreates the three schemas.
-- snapshot_month is the first day of the month. Power Query builds the month-end date key.
\set ON_ERROR_STOP on

DROP SCHEMA IF EXISTS hr CASCADE;
DROP SCHEMA IF EXISTS org CASCADE;
DROP SCHEMA IF EXISTS security CASCADE;
CREATE SCHEMA org;
CREATE SCHEMA hr;
CREATE SCHEMA security;

-- ---------- organisations ----------
CREATE TABLE org.organisations (
    org_id                INT PRIMARY KEY,
    org_name              TEXT NOT NULL UNIQUE,
    industry              TEXT NOT NULL,
    employee_count_band   TEXT NOT NULL,
    country               TEXT NOT NULL,
    subscription_tier     TEXT NOT NULL
);
CREATE TABLE org.departments (
    department_id      INT PRIMARY KEY,
    org_id             INT NOT NULL REFERENCES org.organisations (org_id),
    department_name    TEXT NOT NULL,
    department_group   TEXT NOT NULL,
    cost_centre        TEXT NOT NULL UNIQUE
);

-- ---------- people and monthly history ----------
CREATE TABLE hr.employees (
    employee_id          INT PRIMARY KEY,
    org_id               INT NOT NULL REFERENCES org.organisations (org_id),
    first_name           TEXT NOT NULL,
    last_name            TEXT NOT NULL,
    email                TEXT NOT NULL UNIQUE,
    department_id        INT NOT NULL REFERENCES org.departments (department_id),
    job_level            TEXT NOT NULL,
    employment_type      TEXT NOT NULL,
    hire_date            DATE NOT NULL,
    termination_date     DATE,
    termination_reason   TEXT
);
CREATE TABLE hr.employee_monthly_snapshots (
    snapshot_month     DATE NOT NULL,          -- always the 1st of the month
    employee_id        INT NOT NULL REFERENCES hr.employees (employee_id),
    org_id             INT NOT NULL REFERENCES org.organisations (org_id),
    is_active          BOOLEAN NOT NULL,
    base_salary_usd    NUMERIC(12, 2),         -- null when the employee is not active
    job_level          TEXT NOT NULL,
    department_id      INT NOT NULL REFERENCES org.departments (department_id),
    PRIMARY KEY (employee_id, snapshot_month)
);

-- ---------- leave and reviews ----------
CREATE TABLE hr.leave_records (
    leave_id        INT PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES hr.employees (employee_id),
    org_id          INT NOT NULL REFERENCES org.organisations (org_id),
    leave_type      TEXT NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    days_taken      INT NOT NULL,
    approved_by     INT NOT NULL REFERENCES hr.employees (employee_id)
);
CREATE TABLE hr.performance_reviews (
    review_id      INT PRIMARY KEY,
    employee_id    INT NOT NULL REFERENCES hr.employees (employee_id),
    org_id         INT NOT NULL REFERENCES org.organisations (org_id),
    review_year    INT NOT NULL,
    rating         SMALLINT NOT NULL,
    reviewer_id    INT NOT NULL REFERENCES hr.employees (employee_id)
);

-- ---------- access list (SQL copy only; the model hard-codes this table) ----------
CREATE TABLE security.security_mapping (
    user_email     TEXT PRIMARY KEY,
    org_id         INT NOT NULL REFERENCES org.organisations (org_id),
    access_level   TEXT NOT NULL
);

-- ---------- load the CSV files (mounted at /data in the container) ----------
COPY org.organisations                 FROM '/data/organisations.csv'              WITH (FORMAT csv, HEADER true);
COPY org.departments                   FROM '/data/departments.csv'                WITH (FORMAT csv, HEADER true);
COPY hr.employees                      FROM '/data/employees.csv'                  WITH (FORMAT csv, HEADER true);
COPY hr.employee_monthly_snapshots     FROM '/data/employee_monthly_snapshots.csv' WITH (FORMAT csv, HEADER true);
COPY hr.leave_records                  FROM '/data/leave_records.csv'              WITH (FORMAT csv, HEADER true);
COPY hr.performance_reviews            FROM '/data/performance_reviews.csv'        WITH (FORMAT csv, HEADER true);
COPY security.security_mapping         FROM '/data/security_mapping.csv'           WITH (FORMAT csv, HEADER true);

CREATE INDEX ix_snapshots_month ON hr.employee_monthly_snapshots (snapshot_month);
CREATE INDEX ix_snapshots_org_month ON hr.employee_monthly_snapshots (org_id, snapshot_month);
CREATE INDEX ix_employees_hire ON hr.employees (hire_date);
CREATE INDEX ix_employees_term ON hr.employees (termination_date);
CREATE INDEX ix_leave_start ON hr.leave_records (start_date);

-- Sign-in list for the Tenant Access role. One row per active employee.
-- Active matches dim_employee: no termination date, and the September 2026 snapshot is active.
CREATE VIEW security.security_users AS
SELECT
    e.email,
    e.employee_id,
    e.org_id,
    e.department_id,
    e.job_level,
    CASE e.job_level
        WHEN 'IC1' THEN 1
        WHEN 'IC2' THEN 2
        WHEN 'IC3' THEN 3
        WHEN 'IC4' THEN 4
        WHEN 'M1'  THEN 5
        WHEN 'M2'  THEN 6
        WHEN 'M3'  THEN 7
    END AS level_sort
FROM hr.employees AS e
JOIN hr.employee_monthly_snapshots AS s
    ON s.employee_id = e.employee_id
   AND s.snapshot_month = DATE '2026-09-01'
   AND s.is_active
WHERE e.termination_date IS NULL;

ANALYZE;

-- ---------- row-count check ----------
SELECT 'org.organisations' AS table_name, COUNT(*) AS row_count FROM org.organisations
UNION ALL SELECT 'org.departments',                 COUNT(*) FROM org.departments
UNION ALL SELECT 'hr.employees',                    COUNT(*) FROM hr.employees
UNION ALL SELECT 'hr.employee_monthly_snapshots',   COUNT(*) FROM hr.employee_monthly_snapshots
UNION ALL SELECT 'hr.leave_records',                COUNT(*) FROM hr.leave_records
UNION ALL SELECT 'hr.performance_reviews',          COUNT(*) FROM hr.performance_reviews
UNION ALL SELECT 'security.security_mapping',       COUNT(*) FROM security.security_mapping
UNION ALL SELECT 'security.security_users',          COUNT(*) FROM security.security_users
ORDER BY table_name;
