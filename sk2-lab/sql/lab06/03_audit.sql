-- Lab 06 Step 3 — Run audit + instrumented ETL
CREATE SCHEMA IF NOT EXISTS etl;

CREATE TABLE IF NOT EXISTS etl.run_audit (
    run_id        BIGSERIAL PRIMARY KEY,
    step_name     TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    rows_read     BIGINT,
    rows_loaded   BIGINT,
    rows_rejected BIGINT,
    status        TEXT NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running','success','failed'))
);

-- =============================================================================
-- Instrument the validating load (staging.sales → clean | dead_letter)
-- Requires staging.sales already populated (run 02_dead_letter.sql seed first).
-- =============================================================================
TRUNCATE staging.sales_clean;

INSERT INTO etl.run_audit (step_name) VALUES ('validate_staging_sales');

BEGIN;

WITH classified AS (
    SELECT
        s.order_id, s.order_ts, s.store_id, s.customer_id, s.order_line_id,
        s.product_id, s.quantity, s.unit_price, s.line_amount,
        CASE
            WHEN s.quantity IS NULL OR s.quantity <= 0 THEN 'quantity_not_positive'
            WHEN s.unit_price < 0                        THEN 'negative_unit_price'
            WHEN c.customer_key IS NULL                  THEN 'unknown_customer'
            ELSE NULL
        END AS violation
    FROM staging.sales s
    LEFT JOIN dw.dim_customer c
           ON c.customer_id = s.customer_id AND c.is_current
),
rejected AS (
    INSERT INTO etl.dead_letter (source_table, rule_violated, raw_row)
    SELECT 'staging.sales', violation, to_jsonb(classified) - 'violation'
    FROM classified
    WHERE violation IS NOT NULL
    RETURNING 1
)
INSERT INTO staging.sales_clean (
    order_id, order_ts, store_id, customer_id, order_line_id,
    product_id, quantity, unit_price, line_amount
)
SELECT
    order_id, order_ts, store_id, customer_id, order_line_id,
    product_id, quantity, unit_price, line_amount
FROM classified
WHERE violation IS NULL;

UPDATE etl.run_audit
SET finished_at   = now(),
    rows_read     = (SELECT COUNT(*) FROM staging.sales),
    rows_loaded   = (SELECT COUNT(*) FROM staging.sales_clean),
    rows_rejected = (SELECT COUNT(*) FROM etl.dead_letter
                     WHERE rejected_at >= (SELECT started_at FROM etl.run_audit
                                           WHERE run_id = currval('etl.run_audit_run_id_seq'))),
    status = 'success'
WHERE run_id = currval('etl.run_audit_run_id_seq');

COMMIT;

-- Reconciliation identity: rows_read = rows_loaded + rows_rejected
SELECT
    run_id, step_name, rows_read, rows_loaded, rows_rejected,
    rows_read = rows_loaded + rows_rejected AS balances
FROM etl.run_audit
WHERE run_id = currval('etl.run_audit_run_id_seq');

-- =============================================================================
-- Operator monitoring queries
-- =============================================================================

-- Did last night succeed, and was it normal?
SELECT * FROM etl.run_audit ORDER BY run_id DESC LIMIT 5;

-- Alert condition 1: no successful load in 26 hours
SELECT COUNT(*) = 0 AS should_alert
FROM etl.run_audit
WHERE step_name IN ('validate_staging_sales', 'load_fact_sales')
  AND status = 'success'
  AND finished_at > now() - INTERVAL '26 hours';

-- Alert condition 2: reject rate above 1%
SELECT rows_rejected::numeric / NULLIF(rows_read, 0) > 0.01 AS should_alert
FROM etl.run_audit
ORDER BY run_id DESC
LIMIT 1;

-- =============================================================================
-- Step 4 — Idempotency proof (delete-by-scope reload)
-- Fingerprint = count + sum(line_amount); must match before and after re-run.
-- Scope DELETE by dates in the batch, not calendar "today".
-- =============================================================================

CREATE TEMP TABLE IF NOT EXISTS _idempotency_fingerprint (
    label TEXT PRIMARY KEY,
    n     BIGINT,
    amt   NUMERIC
);

-- Baseline
DELETE FROM _idempotency_fingerprint;
INSERT INTO _idempotency_fingerprint
SELECT 'before', COUNT(*), SUM(line_amount) FROM dw.fact_sales;

-- Rebuild sales_clean as COMPLETE partitions for dates in staging.sales
TRUNCATE staging.sales_clean;
INSERT INTO staging.sales_clean (
    order_id, order_ts, store_id, customer_id, order_line_id,
    product_id, quantity, unit_price, line_amount
)
SELECT
    o.order_id, o.order_ts, o.store_id, o.customer_id, ol.order_line_id,
    ol.product_id, ol.quantity,
    ROUND(ol.line_amount / ol.quantity, 2),
    ol.line_amount
FROM public.orders o
JOIN public.order_lines ol ON ol.order_id = o.order_id
WHERE o.status = 'completed'
  AND o.order_ts::date IN (
      SELECT DISTINCT order_ts::date FROM staging.sales
  );

INSERT INTO etl.run_audit (step_name) VALUES ('idempotent_fact_reload');

BEGIN;

DELETE FROM dw.fact_sales
WHERE date_key IN (
    SELECT DISTINCT TO_CHAR(s.order_ts, 'YYYYMMDD')::int
    FROM staging.sales_clean s
);

INSERT INTO dw.fact_sales (
    date_key, customer_key, product_key, store_key,
    order_id, order_line_id, quantity, unit_price, line_amount
)
SELECT
    TO_CHAR(s.order_ts, 'YYYYMMDD')::int,
    dc.customer_key, dp.product_key, ds.store_key,
    s.order_id, s.order_line_id, s.quantity, s.unit_price, s.line_amount
FROM staging.sales_clean s
JOIN dw.dim_customer dc
  ON dc.customer_id = s.customer_id
 AND s.order_ts::date >= dc.valid_from
 AND s.order_ts::date <  dc.valid_to
JOIN dw.dim_product dp ON dp.product_id = s.product_id AND dp.is_current
JOIN dw.dim_store   ds ON ds.store_id   = s.store_id;

UPDATE etl.run_audit
SET finished_at   = now(),
    rows_read     = (SELECT COUNT(*) FROM staging.sales_clean),
    rows_loaded   = (SELECT COUNT(*) FROM staging.sales_clean),
    rows_rejected = 0,
    status        = 'success'
WHERE run_id = currval('etl.run_audit_run_id_seq');

COMMIT;

INSERT INTO _idempotency_fingerprint
SELECT 'after', COUNT(*), SUM(line_amount) FROM dw.fact_sales;

-- Pass when count and sum are unchanged
SELECT
    b.n AS before_count, a.n AS after_count,
    b.amt AS before_sum, a.amt AS after_sum,
    (b.n = a.n AND b.amt = a.amt) AS idempotent_pass
FROM _idempotency_fingerprint b
JOIN _idempotency_fingerprint a ON a.label = 'after'
WHERE b.label = 'before';
