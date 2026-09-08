INSERT INTO dw.dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::int          AS date_key,
    d::date                              AS full_date,
    EXTRACT(YEAR FROM d)::int            AS year,
    EXTRACT(QUARTER FROM d)::int         AS quarter,
    EXTRACT(MONTH FROM d)::int           AS month,
    TO_CHAR(d, 'FMMonth')                AS month_name,
    EXTRACT(DAY FROM d)::int             AS day_of_month,
    EXTRACT(ISODOW FROM d)::int          AS day_of_week,
    TO_CHAR(d, 'FMDay')                  AS day_name,
    EXTRACT(ISODOW FROM d) IN (6,7)      AS is_weekend
FROM generate_series('2023-01-01'::date, '2032-12-31'::date, '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

SELECT COUNT(*), MIN(full_date), MAX(full_date) FROM dw.dim_date;


--- INITIAL LOADS
INSERT INTO dw.dim_store (store_id, store_name, region)
SELECT store_id, store_name, region FROM public.stores
ORDER BY store_id;

INSERT INTO dw.dim_product (product_id, product_name, category, unit_price, valid_from)
SELECT product_id, product_name, category, unit_price, '1900-01-01'
FROM public.products
ORDER BY product_id;

SELECT COUNT(*) FROM dw.dim_product WHERE is_current;

INSERT INTO dw.dim_customer (customer_id, full_name, email, city, segment, valid_from)
SELECT customer_id, full_name, email, city, segment, '1900-01-01'
FROM public.customers
ORDER BY customer_id;

SELECT COUNT(*) FROM dw.dim_customer WHERE is_current;


--- INCREMENTAL LOADS
BEGIN;

-- 4a. Detect rows whose SCD2-tracked attributes changed
WITH changed AS (
    SELECT s.customer_id, s.full_name, s.email, s.city, s.segment
    FROM public.customers s
    JOIN dw.dim_customer d
      ON d.customer_id = s.customer_id AND d.is_current
    WHERE s.city    IS DISTINCT FROM d.city
       OR s.segment IS DISTINCT FROM d.segment
)
-- 4b. Close the current versions
UPDATE dw.dim_customer d
SET valid_to = CURRENT_DATE, is_current = FALSE
FROM changed c
WHERE d.customer_id = c.customer_id AND d.is_current;

-- 4c. Insert new versions for changed rows + brand-new customers
INSERT INTO dw.dim_customer (customer_id, full_name, email, city, segment, valid_from)
SELECT s.customer_id, s.full_name, s.email, s.city, s.segment, CURRENT_DATE
FROM public.customers s
LEFT JOIN dw.dim_customer d
       ON d.customer_id = s.customer_id AND d.is_current
WHERE d.customer_id IS NULL;            -- no current row: either just closed, or new

COMMIT;

UPDATE public.customers SET city = 'Accra', segment = 'Premium' WHERE customer_id = 42;
-- now rerun the whole Step 4 block
SELECT customer_key, city, segment, valid_from, valid_to, is_current
FROM dw.dim_customer WHERE customer_id = 42 ORDER BY valid_from;


--- ETL CONTROL
CREATE TABLE IF NOT EXISTS dw.etl_control (
    table_name      TEXT PRIMARY KEY,
    high_water_mark TIMESTAMPTZ NOT NULL
);
INSERT INTO dw.etl_control VALUES ('fact_sales', '1900-01-01')
ON CONFLICT (table_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.etl_run_log (
    run_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_name   TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    rows_loaded  BIGINT,
    status       TEXT NOT NULL DEFAULT 'running'   -- running | success | failed
);

SELECT * FROM dw.etl_control;


--- INCREMENTAL IDEMPOTENT LOAD (instrumented with etl.run_audit)
-- Assumes etl.run_audit exists (create via lab06/03_audit.sql).
CREATE SCHEMA IF NOT EXISTS etl;

INSERT INTO etl.run_audit (step_name) VALUES ('load_fact_sales');

BEGIN;

INSERT INTO dw.etl_run_log (table_name) VALUES ('fact_sales');

WITH mark AS (
    SELECT high_water_mark FROM dw.etl_control WHERE table_name = 'fact_sales'
),
new_lines AS (
    SELECT o.order_id, o.order_ts, o.store_id, o.customer_id,
           ol.order_line_id, ol.product_id, ol.quantity, ol.line_amount,
           ROUND(ol.line_amount / ol.quantity, 2) AS unit_price
    FROM public.orders o
    JOIN public.order_lines ol ON ol.order_id = o.order_id
    CROSS JOIN mark m
    WHERE o.status = 'completed'
      AND o.order_ts > m.high_water_mark
),
inserted AS (
    INSERT INTO dw.fact_sales
        (date_key, customer_key, product_key, store_key,
         order_id, order_line_id, quantity, unit_price, line_amount)
    SELECT
        TO_CHAR(nl.order_ts, 'YYYYMMDD')::int,
        dc.customer_key, dp.product_key, ds.store_key,
        nl.order_id, nl.order_line_id, nl.quantity, nl.unit_price, nl.line_amount
    FROM new_lines nl
    JOIN dw.dim_customer dc ON dc.customer_id = nl.customer_id
                           AND nl.order_ts::date >= dc.valid_from
                           AND nl.order_ts::date <  dc.valid_to
    JOIN dw.dim_product  dp ON dp.product_id = nl.product_id AND dp.is_current
    JOIN dw.dim_store    ds ON ds.store_id   = nl.store_id
    ON CONFLICT (order_line_id) DO NOTHING
    RETURNING 1
),
audited AS (
    UPDATE etl.run_audit
    SET finished_at   = now(),
        rows_read     = (SELECT COUNT(*) FROM new_lines),
        rows_loaded   = (SELECT COUNT(*) FROM inserted),
        rows_rejected = (SELECT COUNT(*) FROM new_lines)
                      - (SELECT COUNT(*) FROM inserted),
        status        = 'success'
    WHERE run_id = currval('etl.run_audit_run_id_seq')
    RETURNING run_id
)
UPDATE dw.etl_control
SET high_water_mark = COALESCE(
        (SELECT MAX(order_ts) FROM public.orders WHERE status = 'completed'),
        high_water_mark)
WHERE table_name = 'fact_sales';

UPDATE dw.etl_run_log
SET finished_at = now(), status = 'success',
    rows_loaded = (SELECT COUNT(*) FROM dw.fact_sales)
WHERE run_id = (SELECT MAX(run_id) FROM dw.etl_run_log);

COMMIT;

SELECT * FROM etl.run_audit WHERE step_name = 'load_fact_sales' ORDER BY run_id DESC LIMIT 1;

SELECT COUNT(*) FROM dw.fact_sales;
SELECT SUM(line_amount) FROM dw.fact_sales;
SELECT * FROM dw.etl_control;

SELECT * FROM dw.etl_run_log ORDER BY run_id DESC LIMIT 1;


--- SIMULATE UPDATE FOR NEXT RUN
-- New business arrives:
INSERT INTO public.orders (customer_id, store_id, order_ts, status)
VALUES (42, 3, now(), 'completed');
INSERT INTO public.order_lines (order_id, product_id, quantity, line_amount)
SELECT MAX(order_id), 7, 2, 19.98 FROM public.orders;

SELECT f.order_id, c.city, c.segment
FROM dw.fact_sales f JOIN dw.dim_customer c USING (customer_key)
WHERE f.order_id = (SELECT MAX(order_id) FROM public.orders);