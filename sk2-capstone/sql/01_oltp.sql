-- MedInsure OLTP source schema + full-volume synthetic seed (Deliverable 2 prep)
-- Volumes (brief targets):
--   plan_types 8 | diagnosis ~12k | procedure 8.5k | members 500k | member_plan_history 750k
--   providers 15k | provider_network_history 22k | claims 2M | claim_lines ~7.5M
-- Run: psql -h localhost -p 5432 -U postgres -d medinsure -f sql/01_oltp.sql
-- Expect a long runtime on a laptop (often 15–45+ minutes).

\timing on
SET client_min_messages TO WARNING;
SET synchronous_commit TO OFF;
SET maintenance_work_mem TO '1GB';
SET work_mem TO '256MB';

DROP TABLE IF EXISTS public.claim_lines CASCADE;
DROP TABLE IF EXISTS public.claims CASCADE;
DROP TABLE IF EXISTS public.member_plan_history CASCADE;
DROP TABLE IF EXISTS public.provider_network_history CASCADE;
DROP TABLE IF EXISTS public.members CASCADE;
DROP TABLE IF EXISTS public.providers CASCADE;
DROP TABLE IF EXISTS public.diagnosis_codes CASCADE;
DROP TABLE IF EXISTS public.procedure_codes CASCADE;
DROP TABLE IF EXISTS public.plan_types CASCADE;

-- ---------------------------------------------------------------------------
-- DDL
-- ---------------------------------------------------------------------------
CREATE TABLE public.plan_types (
    plan_id      SERIAL PRIMARY KEY,
    plan_code    VARCHAR(20) NOT NULL UNIQUE,
    plan_name    VARCHAR(100) NOT NULL,
    plan_type    VARCHAR(20) NOT NULL CHECK (plan_type IN ('HMO', 'PPO', 'EPO', 'HDHP')),
    deductible   NUMERIC(10,2) NOT NULL CHECK (deductible >= 0),
    oop_max      NUMERIC(10,2) NOT NULL CHECK (oop_max >= 0)
);

CREATE TABLE public.diagnosis_codes (
    diagnosis_code VARCHAR(10) PRIMARY KEY,
    description    VARCHAR(200) NOT NULL,
    category       VARCHAR(80) NOT NULL
);

CREATE TABLE public.procedure_codes (
    procedure_code VARCHAR(10) PRIMARY KEY,
    description    VARCHAR(200) NOT NULL,
    category       VARCHAR(80) NOT NULL
);

CREATE TABLE public.members (
    member_id       SERIAL PRIMARY KEY,
    first_name      VARCHAR(60) NOT NULL,
    last_name       VARCHAR(60) NOT NULL,
    date_of_birth   DATE NOT NULL,
    gender          CHAR(1) NOT NULL CHECK (gender IN ('F', 'M', 'U')),
    state           CHAR(2) NOT NULL,
    zip_code        VARCHAR(10) NOT NULL,
    plan_id         INT NOT NULL REFERENCES public.plan_types (plan_id),
    enrollment_date DATE NOT NULL
);

CREATE TABLE public.member_plan_history (
    history_id      BIGSERIAL PRIMARY KEY,
    member_id       INT NOT NULL REFERENCES public.members (member_id),
    plan_id         INT NOT NULL REFERENCES public.plan_types (plan_id),
    state           CHAR(2) NOT NULL,
    zip_code        VARCHAR(10) NOT NULL,
    effective_start DATE NOT NULL,
    effective_end   DATE NOT NULL,
    CHECK (effective_start <= effective_end)
);

CREATE TABLE public.providers (
    provider_id            SERIAL PRIMARY KEY,
    provider_name          VARCHAR(120) NOT NULL,
    provider_type          VARCHAR(40) NOT NULL CHECK (provider_type IN ('physician', 'hospital', 'facility')),
    specialty              VARCHAR(60) NOT NULL,
    network_status         VARCHAR(20) NOT NULL CHECK (network_status IN ('in_network', 'out_of_network')),
    network_effective_date DATE NOT NULL
);

CREATE TABLE public.provider_network_history (
    history_id      BIGSERIAL PRIMARY KEY,
    provider_id     INT NOT NULL REFERENCES public.providers (provider_id),
    specialty       VARCHAR(60) NOT NULL,
    network_status  VARCHAR(20) NOT NULL CHECK (network_status IN ('in_network', 'out_of_network')),
    effective_start DATE NOT NULL,
    effective_end   DATE NOT NULL,
    CHECK (effective_start <= effective_end)
);

-- FKs to diagnosis added after seed for load speed
CREATE TABLE public.claims (
    claim_id                 BIGSERIAL PRIMARY KEY,
    member_id                INT NOT NULL,
    provider_id              INT NOT NULL,
    plan_id                  INT NOT NULL,
    service_date             DATE NOT NULL,
    processed_date           DATE NOT NULL,
    claim_type               VARCHAR(30) NOT NULL CHECK (claim_type IN ('professional', 'institutional', 'pharmacy_medical')),
    claim_status             VARCHAR(20) NOT NULL CHECK (claim_status IN ('paid', 'denied', 'partial')),
    primary_diagnosis_code   VARCHAR(10) NOT NULL,
    total_allowed            NUMERIC(12,2) NOT NULL CHECK (total_allowed >= 0),
    total_paid               NUMERIC(12,2) NOT NULL CHECK (total_paid >= 0),
    CHECK (processed_date >= service_date)
);

CREATE TABLE public.claim_lines (
    claim_line_id   BIGSERIAL PRIMARY KEY,
    claim_id        BIGINT NOT NULL,
    line_number     SMALLINT NOT NULL CHECK (line_number > 0),
    procedure_code  VARCHAR(10) NOT NULL,
    line_allowed    NUMERIC(12,2) NOT NULL CHECK (line_allowed >= 0),
    line_paid       NUMERIC(12,2) NOT NULL CHECK (line_paid >= 0)
);

-- ---------------------------------------------------------------------------
-- Seed small references
-- ---------------------------------------------------------------------------
INSERT INTO public.plan_types (plan_code, plan_name, plan_type, deductible, oop_max) VALUES
    ('HMO-BASIC',  'MedInsure HMO Basic',      'HMO',  1500,  6000),
    ('HMO-PLUS',   'MedInsure HMO Plus',       'HMO',  1000,  5000),
    ('PPO-STD',    'MedInsure PPO Standard',   'PPO',  2000,  7000),
    ('PPO-PREM',   'MedInsure PPO Premium',    'PPO',  1000,  4500),
    ('EPO-CORE',   'MedInsure EPO Core',       'EPO',  1750,  6500),
    ('EPO-ADV',    'MedInsure EPO Advantage',  'EPO',  1250,  5500),
    ('HDHP-IND',   'MedInsure HDHP Individual','HDHP', 3000,  7500),
    ('HDHP-FAM',   'MedInsure HDHP Family',    'HDHP', 6000, 14000);

-- 12,000 unique ICD-like codes: Letter + 3 digits + . + digit
INSERT INTO public.diagnosis_codes (diagnosis_code, description, category)
SELECT
    chr(65 + ((gs - 1) / 1000) % 26)
        || lpad((((gs - 1) % 1000))::text, 3, '0')
        || '.' || ((gs - 1) % 10)::text,
    'Synthetic diagnosis ' || gs,
    (ARRAY[
        'Infectious','Neoplasms','Endocrine','Mental Health','Circulatory',
        'Respiratory','Digestive','Musculoskeletal','Injury','Pregnancy',
        'Symptoms','Factors'
    ])[1 + ((gs - 1) % 12)]
FROM generate_series(1, 12000) AS gs;

INSERT INTO public.procedure_codes (procedure_code, description, category)
SELECT
    lpad((10000 + gs)::text, 5, '0'),
    'Synthetic procedure ' || gs,
    (ARRAY[
        'Evaluation','Surgery','Radiology','Pathology','Medicine',
        'Anesthesia','Physical Therapy','Emergency'
    ])[1 + ((gs - 1) % 8)]
FROM generate_series(1, 8500) AS gs;

-- ---------------------------------------------------------------------------
-- Members (500k) + plan history (750k)
-- ---------------------------------------------------------------------------
INSERT INTO public.members (
    first_name, last_name, date_of_birth, gender, state, zip_code, plan_id, enrollment_date
)
SELECT
    'Member' || gs,
    'Test' || (gs % 10000),
    DATE '1950-01-01' + ((gs % 20000))::int,
    (ARRAY['F', 'M', 'U'])[1 + (gs % 3)],
    (ARRAY['CA','TX','NY','FL','IL','PA','OH','GA','NC','MI'])[1 + (gs % 10)],
    lpad((10000 + (gs % 90000))::text, 5, '0'),
    1 + (gs % 8),
    DATE '2018-01-01' + ((gs % 2500))::int
FROM generate_series(1, 500000) AS gs;

INSERT INTO public.member_plan_history (
    member_id, plan_id, state, zip_code, effective_start, effective_end
)
SELECT
    m.member_id, m.plan_id, m.state, m.zip_code, m.enrollment_date,
    CASE WHEN m.member_id <= 250000 THEN m.enrollment_date + 400 ELSE DATE '9999-12-31' END
FROM public.members m;

INSERT INTO public.member_plan_history (
    member_id, plan_id, state, zip_code, effective_start, effective_end
)
SELECT
    m.member_id,
    1 + (m.plan_id % 8),
    (ARRAY['CA','TX','NY','FL','IL','PA','OH','GA','NC','MI'])[1 + ((m.member_id + 3) % 10)],
    lpad((20000 + (m.member_id % 80000))::text, 5, '0'),
    m.enrollment_date + 401,
    DATE '9999-12-31'
FROM public.members m
WHERE m.member_id <= 250000;

UPDATE public.members m
SET plan_id = h.plan_id,
    state = h.state,
    zip_code = h.zip_code
FROM public.member_plan_history h
WHERE h.member_id = m.member_id
  AND h.effective_end = DATE '9999-12-31';

-- ---------------------------------------------------------------------------
-- Providers (15k) + network history (22k)
-- ---------------------------------------------------------------------------
INSERT INTO public.providers (
    provider_name, provider_type, specialty, network_status, network_effective_date
)
SELECT
    'Provider ' || gs,
    (ARRAY['physician', 'hospital', 'facility'])[1 + (gs % 3)],
    (ARRAY[
        'Cardiology','Orthopedics','Family Medicine','Internal Medicine',
        'Emergency','Radiology','Oncology','Pediatrics','Dermatology','Neurology'
    ])[1 + (gs % 10)],
    CASE WHEN gs % 5 = 0 THEN 'out_of_network' ELSE 'in_network' END,
    DATE '2015-01-01' + ((gs % 3000))::int
FROM generate_series(1, 15000) AS gs;

INSERT INTO public.provider_network_history (
    provider_id, specialty, network_status, effective_start, effective_end
)
SELECT
    p.provider_id, p.specialty, p.network_status, p.network_effective_date,
    CASE WHEN p.provider_id <= 7000 THEN p.network_effective_date + 700 ELSE DATE '9999-12-31' END
FROM public.providers p;

INSERT INTO public.provider_network_history (
    provider_id, specialty, network_status, effective_start, effective_end
)
SELECT
    p.provider_id,
    (ARRAY[
        'Cardiology','Orthopedics','Family Medicine','Internal Medicine',
        'Emergency','Radiology','Oncology','Pediatrics','Dermatology','Neurology'
    ])[1 + ((p.provider_id + 2) % 10)],
    CASE WHEN p.network_status = 'in_network' THEN 'out_of_network' ELSE 'in_network' END,
    p.network_effective_date + 701,
    DATE '9999-12-31'
FROM public.providers p
WHERE p.provider_id <= 7000;

UPDATE public.providers p
SET specialty = h.specialty,
    network_status = h.network_status
FROM public.provider_network_history h
WHERE h.provider_id = p.provider_id
  AND h.effective_end = DATE '9999-12-31';

-- ---------------------------------------------------------------------------
-- Claims (2,000,000) — diagnosis via numbered array join (no per-row OFFSET)
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE tmp_diagnosis AS
SELECT diagnosis_code,
       row_number() OVER (ORDER BY diagnosis_code) AS rn
FROM public.diagnosis_codes;

CREATE TEMP TABLE tmp_procedure AS
SELECT procedure_code,
       row_number() OVER (ORDER BY procedure_code) AS rn
FROM public.procedure_codes;

ANALYZE tmp_diagnosis;
ANALYZE tmp_procedure;

INSERT INTO public.claims (
    member_id, provider_id, plan_id, service_date, processed_date,
    claim_type, claim_status, primary_diagnosis_code, total_allowed, total_paid
)
SELECT
    1 + ((gs - 1) % 500000),
    1 + ((gs - 1) % 15000),
    1 + ((gs - 1) % 8),
    DATE '2022-01-01' + ((gs * 17) % 1400),
    DATE '2022-01-01' + ((gs * 17) % 1400) + (gs % 14),
    (ARRAY['professional', 'institutional', 'pharmacy_medical'])[1 + (gs % 3)],
    CASE
        WHEN gs % 11 = 0 THEN 'denied'
        WHEN gs % 17 = 0 THEN 'partial'
        ELSE 'paid'
    END,
    d.diagnosis_code,
    ROUND((50 + (gs % 9500))::numeric, 2),
    CASE
        WHEN gs % 11 = 0 THEN 0
        WHEN gs % 17 = 0 THEN ROUND((50 + (gs % 9500))::numeric * 0.50, 2)
        ELSE ROUND((50 + (gs % 9500))::numeric * (0.70 + (gs % 25) * 0.01), 2)
    END
FROM generate_series(1, 2000000) AS gs
CROSS JOIN (SELECT COUNT(*)::int AS n FROM tmp_diagnosis) dc
JOIN tmp_diagnosis d ON d.rn = 1 + ((gs - 1) % dc.n);

-- ---------------------------------------------------------------------------
-- Claim lines (~7.5M): 3 or 4 lines per claim → average 3.75 * 2M = 7.5M
-- ---------------------------------------------------------------------------
INSERT INTO public.claim_lines (
    claim_id, line_number, procedure_code, line_allowed, line_paid
)
SELECT
    c.claim_id,
    ln AS line_number,
    p.procedure_code,
    ROUND((c.total_allowed / lc.line_cnt)::numeric, 2),
    ROUND((c.total_paid / lc.line_cnt)::numeric, 2)
FROM public.claims c
CROSS JOIN (SELECT COUNT(*)::int AS n FROM tmp_procedure) pc
CROSS JOIN LATERAL (
    -- 75% get 4 lines, 25% get 3 → avg 3.75 → ~7.5M rows
    SELECT CASE WHEN c.claim_id % 4 = 0 THEN 3 ELSE 4 END AS line_cnt
) lc
CROSS JOIN LATERAL generate_series(1, lc.line_cnt) AS ln
JOIN tmp_procedure p
  ON p.rn = 1 + (((c.claim_id::int + ln) - 1) % pc.n);
-- ---------------------------------------------------------------------------
-- Integrity: FKs + supporting indexes (after bulk load)
-- ---------------------------------------------------------------------------
ALTER TABLE public.claims
    ADD CONSTRAINT claims_member_id_fkey
        FOREIGN KEY (member_id) REFERENCES public.members (member_id),
    ADD CONSTRAINT claims_provider_id_fkey
        FOREIGN KEY (provider_id) REFERENCES public.providers (provider_id),
    ADD CONSTRAINT claims_plan_id_fkey
        FOREIGN KEY (plan_id) REFERENCES public.plan_types (plan_id),
    ADD CONSTRAINT claims_primary_diagnosis_code_fkey
        FOREIGN KEY (primary_diagnosis_code) REFERENCES public.diagnosis_codes (diagnosis_code);

ALTER TABLE public.claim_lines
    ADD CONSTRAINT claim_lines_claim_id_fkey
        FOREIGN KEY (claim_id) REFERENCES public.claims (claim_id),
    ADD CONSTRAINT claim_lines_procedure_code_fkey
        FOREIGN KEY (procedure_code) REFERENCES public.procedure_codes (procedure_code),
    ADD CONSTRAINT claim_lines_claim_line_unique
        UNIQUE (claim_id, line_number);

CREATE INDEX idx_members_plan ON public.members (plan_id);
CREATE INDEX idx_mph_member ON public.member_plan_history (member_id, effective_start, effective_end);
CREATE INDEX idx_pnh_provider ON public.provider_network_history (provider_id, effective_start, effective_end);
CREATE INDEX idx_claims_member ON public.claims (member_id);
CREATE INDEX idx_claims_provider ON public.claims (provider_id);
CREATE INDEX idx_claims_processed ON public.claims (processed_date);
CREATE INDEX idx_claims_service ON public.claims (service_date);
CREATE INDEX idx_claim_lines_claim ON public.claim_lines (claim_id);

ANALYZE public.plan_types;
ANALYZE public.diagnosis_codes;
ANALYZE public.procedure_codes;
ANALYZE public.members;
ANALYZE public.member_plan_history;
ANALYZE public.providers;
ANALYZE public.provider_network_history;
ANALYZE public.claims;
ANALYZE public.claim_lines;

-- ---------------------------------------------------------------------------
-- Verification counts
-- ---------------------------------------------------------------------------
SELECT 'plan_types' AS table_name, COUNT(*) AS n FROM public.plan_types
UNION ALL SELECT 'diagnosis_codes', COUNT(*) FROM public.diagnosis_codes
UNION ALL SELECT 'procedure_codes', COUNT(*) FROM public.procedure_codes
UNION ALL SELECT 'members', COUNT(*) FROM public.members
UNION ALL SELECT 'member_plan_history', COUNT(*) FROM public.member_plan_history
UNION ALL SELECT 'providers', COUNT(*) FROM public.providers
UNION ALL SELECT 'provider_network_history', COUNT(*) FROM public.provider_network_history
UNION ALL SELECT 'claims', COUNT(*) FROM public.claims
UNION ALL SELECT 'claim_lines', COUNT(*) FROM public.claim_lines
ORDER BY 1;
