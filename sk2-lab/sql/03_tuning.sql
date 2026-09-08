EXPLAIN ANALYZE
SELECT * FROM orders WHERE customer_id = 42;


CREATE INDEX idx_orders_customer_id ON orders (customer_id);

EXPLAIN ANALYZE
SELECT * FROM orders WHERE customer_id = 42;


CREATE INDEX idx_order_lines_order_id   ON order_lines (order_id);
CREATE INDEX idx_order_lines_product_id ON order_lines (product_id);
CREATE INDEX idx_orders_store_id        ON orders (store_id);
CREATE INDEX idx_orders_order_ts        ON orders (order_ts);


CREATE INDEX idx_orders_store_ts ON orders (store_id, order_ts);

EXPLAIN ANALYZE
SELECT COUNT(*) FROM orders
WHERE store_id = 3
  AND order_ts >= '2025-01-01' AND order_ts < '2025-02-01';


EXPLAIN (ANALYZE, BUFFERS)
SELECT s.region, DATE_TRUNC('month', o.order_ts)::date AS month,
       SUM(ol.line_amount) AS revenue
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
JOIN stores s       ON s.store_id = o.store_id
WHERE o.status = 'completed'
GROUP BY 1, 2;


CREATE MATERIALIZED VIEW mv_monthly_region_revenue AS
SELECT s.region, DATE_TRUNC('month', o.order_ts)::date AS month,
       SUM(ol.line_amount) AS revenue,
       COUNT(DISTINCT o.order_id) AS orders
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
JOIN stores s       ON s.store_id = o.store_id
WHERE o.status = 'completed'
GROUP BY 1, 2;

-- The dashboard now reads this instead:
SELECT * FROM mv_monthly_region_revenue ORDER BY month, region;


-- Step 7 — Measure index write cost, then clean up

-- \timing on

-- A) INSERT WITH indexes
INSERT INTO orders (customer_id, store_id, order_ts, status)
SELECT 1 + (random()*1999)::int, 1 + (random()*7)::int, now(), 'completed'
FROM generate_series(1, 10000);
-- Time: 150.866 ms

-- Drop the four secondary indexes
DROP INDEX idx_orders_customer_id;
DROP INDEX idx_orders_store_id;
DROP INDEX idx_orders_order_ts;
DROP INDEX idx_orders_store_ts;

-- B) INSERT WITHOUT indexes 
INSERT INTO orders (customer_id, store_id, order_ts, status)
SELECT 1 + (random()*1999)::int, 1 + (random()*7)::int, now(), 'completed'
FROM generate_series(1, 10000);
-- Time: 107.057 ms

-- Recreate indexes
CREATE INDEX idx_orders_customer_id ON orders (customer_id);
CREATE INDEX idx_orders_store_id    ON orders (store_id);
CREATE INDEX idx_orders_order_ts    ON orders (order_ts);
CREATE INDEX idx_orders_store_ts    ON orders (store_id, order_ts);

-- Remove both test batches
DELETE FROM orders
WHERE order_ts >= now() - INTERVAL '10 minutes'
  AND order_id > 50000;

-- Verify: back to ~50,000 orders
SELECT COUNT(*) FROM orders;
-- \di orders*
