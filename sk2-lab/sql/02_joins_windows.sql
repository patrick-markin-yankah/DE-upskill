SELECT o.order_id, o.order_ts, s.store_name, s.region
FROM orders o
INNER JOIN stores s ON s.store_id = o.store_id
LIMIT 10;


SELECT
    s.region,
    COUNT(DISTINCT o.order_id)      AS orders,
    SUM(ol.line_amount)             AS revenue,
    ROUND(AVG(ol.line_amount), 2)   AS avg_line_value
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
JOIN stores s       ON s.store_id  = o.store_id
WHERE o.status = 'completed'
GROUP BY s.region
ORDER BY revenue DESC;


SELECT SUM(line_amount) FROM order_lines ol JOIN orders o USING (order_id) WHERE o.status='completed';


SELECT c.customer_id, c.full_name, c.signup_date
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.signup_date;


SELECT COUNT(DISTINCT customer_id) FROM orders;


-- WRONG on purpose: revenue "by order" joining through order_lines twice
SELECT SUM(ol.line_amount) AS looks_like_revenue
FROM orders o
JOIN order_lines ol  ON ol.order_id = o.order_id
JOIN order_lines ol2 ON ol2.order_id = o.order_id;   -- second join multiplies!


WITH order_totals AS (
    SELECT order_id, SUM(line_amount) AS order_total
    FROM order_lines
    GROUP BY order_id                 -- now order_id is unique
)
SELECT SUM(ot.order_total) AS real_revenue
FROM orders o
JOIN order_totals ot ON ot.order_id = o.order_id
WHERE o.status = 'completed';


WITH monthly AS (
    SELECT
        DATE_TRUNC('month', o.order_ts)::date AS month,
        SUM(ol.line_amount)                   AS revenue
    FROM orders o
    JOIN order_lines ol ON ol.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY 1
)
SELECT * FROM monthly ORDER BY month;


WITH monthly AS (
    SELECT DATE_TRUNC('month', o.order_ts)::date AS month,
           SUM(ol.line_amount) AS revenue
    FROM orders o
    JOIN order_lines ol ON ol.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY 1
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month)                        AS prev_month,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
          / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 1) AS growth_pct
FROM monthly
ORDER BY month;


WITH customer_store_rev AS (
    SELECT o.store_id, o.customer_id, SUM(ol.line_amount) AS revenue
    FROM orders o
    JOIN order_lines ol ON ol.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.store_id, o.customer_id
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY revenue DESC) AS rn
    FROM customer_store_rev
)
SELECT s.store_name, c.full_name, r.revenue, r.rn
FROM ranked r
JOIN stores s    ON s.store_id = r.store_id
JOIN customers c ON c.customer_id = r.customer_id
WHERE r.rn <= 3
ORDER BY s.store_name, r.rn;


WITH daily AS (
    SELECT o.order_ts::date AS day, SUM(ol.line_amount) AS revenue
    FROM orders o
    JOIN order_lines ol ON ol.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY 1
)
SELECT
    day,
    revenue,
    SUM(revenue) OVER (ORDER BY day)                       AS running_total,
    ROUND(AVG(revenue) OVER (
        ORDER BY day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)      AS ma_7d
FROM daily
ORDER BY day;