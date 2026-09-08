-- Add unit_price to existing fact_sales (transactional price at sale)
ALTER TABLE dw.fact_sales
    ADD COLUMN IF NOT EXISTS unit_price NUMERIC(10,2);

UPDATE dw.fact_sales
SET unit_price = ROUND(line_amount / quantity, 2)
WHERE unit_price IS NULL;

ALTER TABLE dw.fact_sales
    ALTER COLUMN unit_price SET NOT NULL;


-- Facts: business-rule checks
ALTER TABLE dw.fact_sales
    ADD CONSTRAINT chk_quantity_positive CHECK (quantity > 0),
    ADD CONSTRAINT chk_unit_price_non_negative CHECK (unit_price >= 0);

-- SCD2 hygiene: exactly one current row per business key
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_customer_current
    ON dw.dim_customer (customer_id) WHERE is_current;

-- Referential integrity (if not already present from Lab 04)
ALTER TABLE dw.fact_sales
    ADD CONSTRAINT fk_sales_customer FOREIGN KEY (customer_key)
        REFERENCES dw.dim_customer (customer_key);


INSERT INTO dw.fact_sales (date_key, customer_key, product_key, quantity, unit_price, line_amount)
VALUES (20260101, 1, 1, -5, 10, -50);
-- ERROR:  new row ... violates check constraint "chk_quantity_positive"