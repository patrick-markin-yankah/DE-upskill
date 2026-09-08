CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS etl;

CREATE TABLE IF NOT EXISTS etl.dead_letter (
    dead_letter_id  BIGSERIAL PRIMARY KEY,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_table    TEXT NOT NULL,
    rule_violated   TEXT NOT NULL,
    raw_row         JSONB NOT NULL
);

-- Raw landing: same columns as the Lab 05 fact extract
CREATE TABLE IF NOT EXISTS staging.sales (
    order_id      INT,
    order_ts      TIMESTAMPTZ,
    store_id      INT,
    customer_id   INT,
    order_line_id INT,
    product_id    INT,
    quantity      INT,
    unit_price    NUMERIC(10,2),
    line_amount   NUMERIC(12,2)
);

-- Passed rows only (no violation column)
CREATE TABLE IF NOT EXISTS staging.sales_clean (
    LIKE staging.sales INCLUDING DEFAULTS
);

-- Seed staging from OLTP + a few intentional bad rows (safe to re-run)
TRUNCATE staging.sales, staging.sales_clean;

INSERT INTO staging.sales (
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
LIMIT 1000;

INSERT INTO staging.sales VALUES
    (999001, now(), 1, 42,     900001, 1, -5,   10.00, -50.00),  -- quantity_not_positive
    (999002, now(), 1, 42,     900002, 1,  2,  -10.00, -20.00),  -- negative_unit_price
    (999003, now(), 1, 999999, 900003, 1,  1,   10.00,  10.00);  -- unknown_customer

-- Validating load
WITH classified AS (
    SELECT
        s.*,
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
    SELECT
        'staging.sales',
        violation,
        to_jsonb(classified)
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

-- Sanity check
SELECT
    (SELECT COUNT(*) FROM staging.sales)       AS staged,
    (SELECT COUNT(*) FROM staging.sales_clean) AS clean,
    (SELECT COUNT(*) FROM etl.dead_letter)     AS rejected;

SELECT rule_violated, COUNT(*) 
FROM etl.dead_letter
GROUP BY rule_violated
ORDER BY 1;
