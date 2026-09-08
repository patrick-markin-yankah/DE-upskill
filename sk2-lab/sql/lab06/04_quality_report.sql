-- Lab 06 Step 5 — Quality report (cross-row invariants constraints can't express)
WITH checks AS (
    SELECT 'fact_sales.no_orphan_customers' AS check_name,
           COUNT(*) AS failed
    FROM dw.fact_sales f
    LEFT JOIN dw.dim_customer c ON c.customer_key = f.customer_key
    WHERE c.customer_key IS NULL

    UNION ALL
    SELECT 'dim_customer.one_current_per_id',
           COUNT(*) FROM (
               SELECT customer_id FROM dw.dim_customer
               WHERE is_current
               GROUP BY customer_id
               HAVING COUNT(*) > 1
           ) d

    UNION ALL
    SELECT 'fact_sales.amount_consistency',
           COUNT(*) FROM dw.fact_sales
    WHERE ROUND(quantity * unit_price, 2) <> ROUND(line_amount, 2)

    UNION ALL
    SELECT 'fact_sales.no_future_dates',
           COUNT(*) FROM dw.fact_sales
    WHERE date_key > TO_CHAR(CURRENT_DATE, 'YYYYMMDD')::int
)
SELECT check_name, failed,
       CASE WHEN failed = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks
ORDER BY failed DESC;

-- Alarm test (run separately; always ROLLBACK):
-- BEGIN;
-- DROP INDEX dw.uq_dim_customer_current;  -- Lab 06 unique index blocks the flip otherwise
-- UPDATE dw.dim_customer SET is_current = TRUE
-- WHERE customer_key = (
--     SELECT customer_key FROM dw.dim_customer
--     WHERE customer_id = 42 AND NOT is_current ORDER BY valid_from LIMIT 1);
-- -- re-run the checks CTE above → dim_customer.one_current_per_id should FAIL
-- ROLLBACK;
