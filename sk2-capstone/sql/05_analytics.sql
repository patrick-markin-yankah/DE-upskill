-- MedInsure analytical queries (Deliverable 4)
-- All queries run against dw.* only (not OLTP).
-- Run: psql -h localhost -p 5432 -U postgres -d medinsure -f sql/05_analytics.sql
-- Each query documents: business question + why the warehouse enables it.

\timing on

-- =============================================================================
-- Query 1 — Top 20 providers by total paid, with YoY comparison
-- Business question: Which providers drive the most paid spend this year, and
--   how does that compare to the same providers last year (contract review)?
-- Why warehouse: fact_claim is pre-keyed to dim_provider + dim_date; additive
--   total_paid avoids OLTP joins across claims/providers/history. LAG gives YoY
--   without a self-join explosion on the live 3NF schema.
-- =============================================================================
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


-- =============================================================================
-- Query 2 — Claims paid by ICD-10 diagnosis category, ranked by spend
-- Business question: What did we pay per diagnosis category (Finance / CAO)?
-- Why warehouse: primary diagnosis is already on fact_claim → dim_diagnosis;
--   category is a Type 1 attribute — no ICD reference gymnastics on OLTP.
-- =============================================================================
WITH by_category AS (
    SELECT
        diag.category,
        COUNT(*)            AS claim_count,
        SUM(f.total_paid)   AS total_paid
    FROM dw.fact_claim f
    JOIN dw.dim_diagnosis diag ON diag.diagnosis_key = f.diagnosis_key
    WHERE diag.diagnosis_key <> 0
    GROUP BY diag.category
)
SELECT
    category,
    claim_count,
    total_paid,
    RANK() OVER (ORDER BY total_paid DESC) AS spend_rank
FROM by_category
ORDER BY spend_rank;


-- =============================================================================
-- Query 3 — Member utilization rate by plan type and month
--            (claims per 1,000 members)
-- Business question: How often do members use care by plan type over time?
-- Why warehouse: plan_type lives on dim_plan; member census from dim_member;
--   fact_claim grain is one claim — rates are simple aggregates, not OLTP
--   multi-table joins that crash the live DB.
-- Window: COUNT(*) OVER partitions months observed per plan_type.
-- =============================================================================
WITH claims_by_plan_month AS (
    SELECT
        pl.plan_type,
        d.year,
        d.month,
        COUNT(*) AS claim_count
    FROM dw.fact_claim f
    JOIN dw.dim_plan pl ON pl.plan_key = f.plan_key
    JOIN dw.dim_date d  ON d.date_key = f.service_date_key
    WHERE pl.plan_key <> 0
    GROUP BY pl.plan_type, d.year, d.month
),
member_census AS (
    SELECT
        pl.plan_type,
        COUNT(*) AS member_count
    FROM dw.dim_member m
    JOIN dw.dim_plan pl ON pl.plan_id = m.plan_id AND pl.plan_key <> 0
    WHERE m.is_current
      AND m.member_key <> 0
    GROUP BY pl.plan_type
)
SELECT
    c.plan_type,
    c.year,
    c.month,
    c.claim_count,
    mc.member_count,
    ROUND(1000.0 * c.claim_count / NULLIF(mc.member_count, 0), 2)
        AS claims_per_1000_members,
    COUNT(*) OVER (PARTITION BY c.plan_type) AS months_observed
FROM claims_by_plan_month c
JOIN member_census mc ON mc.plan_type = c.plan_type
ORDER BY c.plan_type, c.year, c.month;


-- =============================================================================
-- Query 4 — Denied claims analysis: denial rate by specialty and claim type
-- Business question: Where are denials concentrated (ops / network management)?
-- Why warehouse: specialty is on the SCD2 provider version linked at service
--   time; claim_status is on the header fact — one GROUP BY, no OLTP history
--   reconstruction.
-- =============================================================================
SELECT
    p.specialty,
    f.claim_type,
    COUNT(*) AS claims,
    COUNT(*) FILTER (WHERE f.claim_status = 'denied') AS denied_claims,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE f.claim_status = 'denied') / NULLIF(COUNT(*), 0),
        2
    ) AS denial_rate_pct
FROM dw.fact_claim f
JOIN dw.dim_provider p ON p.provider_key = f.provider_key
WHERE p.provider_key <> 0
GROUP BY p.specialty, f.claim_type
ORDER BY denial_rate_pct DESC, claims DESC;


-- =============================================================================
-- Query 5 — Out-of-network vs in-network paid amount per member per year
-- Business question: Do we pay more per member for OON care than in-network?
-- Why warehouse: network_status is frozen on the dim_provider version at
--   service time (SCD2) — answers “as of care date,” not only current network.
-- =============================================================================
SELECT
    d.year,
    ROUND(
        SUM(f.total_paid) FILTER (WHERE p.network_status = 'in_network')
            / NULLIF(COUNT(DISTINCT m.member_id) FILTER (WHERE p.network_status = 'in_network'), 0),
        2
    ) AS in_network_paid_per_member,
    ROUND(
        SUM(f.total_paid) FILTER (WHERE p.network_status = 'out_of_network')
            / NULLIF(COUNT(DISTINCT m.member_id) FILTER (WHERE p.network_status = 'out_of_network'), 0),
        2
    ) AS out_of_network_paid_per_member,
    ROUND(
        SUM(CASE WHEN p.network_status = 'in_network' THEN f.total_paid ELSE 0 END),
        2
    ) AS in_network_total_paid,
    ROUND(
        SUM(CASE WHEN p.network_status = 'out_of_network' THEN f.total_paid ELSE 0 END),
        2
    ) AS out_of_network_total_paid
FROM dw.fact_claim f
JOIN dw.dim_provider p ON p.provider_key = f.provider_key
JOIN dw.dim_member m   ON m.member_key = f.member_key
JOIN dw.dim_date d     ON d.date_key = f.service_date_key
WHERE p.provider_key <> 0
  AND m.member_key <> 0
GROUP BY d.year
ORDER BY d.year;


-- =============================================================================
-- Query 6 — Monthly claims volume trend with 3-month moving average
-- Business question: How is claim volume trending (smoothed for seasonality)?
-- Why warehouse: service_date_key → dim_date month attributes; COUNT on
--   fact_claim is a single-table scan vs joining OLTP claims to calendars.
-- =============================================================================
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


-- =============================================================================
-- Query 7 — Member cohort: claims in first 12 months after enrollment,
--            by enrollment year
-- Business question: Do newer enrollment cohorts use more care in year one?
-- Why warehouse: enrollment_date on dim_member + service dates on fact_claim
--   enable cohort windows without reconstructing member history from OLTP
--   plan-change logs by hand.
-- =============================================================================
WITH first_year_claims AS (
    SELECT
        EXTRACT(YEAR FROM m.enrollment_date)::int AS enrollment_year,
        m.member_id,
        f.claim_id,
        COUNT(*) OVER (
            PARTITION BY EXTRACT(YEAR FROM m.enrollment_date)::int, m.member_id
        ) AS claims_in_first_year
    FROM dw.fact_claim f
    JOIN dw.dim_member m ON m.member_key = f.member_key
    JOIN dw.dim_date d   ON d.date_key = f.service_date_key
    WHERE m.member_key <> 0
      AND d.full_date >= m.enrollment_date
      AND d.full_date <  (m.enrollment_date + INTERVAL '12 months')
)
SELECT
    enrollment_year,
    COUNT(DISTINCT member_id) AS members_with_claims,
    COUNT(*)                  AS total_claims,
    ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT member_id), 0), 2)
        AS avg_claims_per_member,
    ROUND(AVG(claims_in_first_year), 2) AS avg_claims_per_member_window
FROM first_year_claims
GROUP BY enrollment_year
ORDER BY enrollment_year;


-- =============================================================================
-- Query 8 — Running cumulative paid by provider YTD; flag when crossing $1M
-- Business question: Which providers cross $1M paid YTD, and on what date?
-- Why warehouse: additive fact_claim.total_paid + dim_date ordering supports
--   cumulative windows; OLTP would need expensive sorted joins each run.
-- =============================================================================
WITH daily_provider AS (
    SELECT
        p.provider_id,
        p.provider_name,
        d.year,
        d.full_date,
        SUM(f.total_paid) AS day_paid
    FROM dw.fact_claim f
    JOIN dw.dim_provider p ON p.provider_key = f.provider_key
    JOIN dw.dim_date d     ON d.date_key = f.service_date_key
    WHERE p.provider_key <> 0
    GROUP BY p.provider_id, p.provider_name, d.year, d.full_date
),
ytd AS (
    SELECT
        provider_id,
        provider_name,
        year,
        full_date,
        day_paid,
        SUM(day_paid) OVER (
            PARTITION BY provider_id, year
            ORDER BY full_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS ytd_paid
    FROM daily_provider
),
flagged AS (
    SELECT
        provider_id,
        provider_name,
        year,
        full_date,
        ROUND(day_paid, 2) AS day_paid,
        ROUND(ytd_paid, 2) AS ytd_paid,
        CASE
            WHEN ytd_paid >= 1000000
             AND COALESCE(
                    LAG(ytd_paid) OVER (
                        PARTITION BY provider_id, year
                        ORDER BY full_date
                    ),
                    0
                ) < 1000000
            THEN TRUE
            ELSE FALSE
        END AS crossed_1m_flag
    FROM ytd
),
year_end AS (
    -- Latest YTD snapshot per provider-year (demonstrates cumulative window)
    SELECT DISTINCT ON (provider_id, year)
        provider_id, provider_name, year, full_date, day_paid, ytd_paid, crossed_1m_flag
    FROM flagged
    ORDER BY provider_id, year, full_date DESC
)
-- Prefer true crossing events; if none at $1M on this seed, show top year-end YTD
SELECT *
FROM flagged
WHERE crossed_1m_flag

UNION ALL

SELECT ye.*
FROM year_end ye
WHERE NOT EXISTS (SELECT 1 FROM flagged WHERE crossed_1m_flag)
ORDER BY year DESC, ytd_paid DESC
LIMIT 30;
