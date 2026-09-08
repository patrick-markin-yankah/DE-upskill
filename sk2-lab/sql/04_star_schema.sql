CREATE TABLE dw.dim_date (
    date_key        INT PRIMARY KEY,          -- YYYYMMDD, e.g. 20250115
    full_date       DATE NOT NULL UNIQUE,
    year            INT  NOT NULL,
    quarter         INT  NOT NULL,
    month           INT  NOT NULL,
    month_name      TEXT NOT NULL,
    day_of_month    INT  NOT NULL,
    day_of_week     INT  NOT NULL,             -- 1 = Monday
    day_name        TEXT NOT NULL,
    is_weekend      BOOLEAN NOT NULL
);

CREATE TABLE dw.dim_customer (
    customer_key    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- surrogate
    customer_id     INT  NOT NULL,            -- natural key from OLTP
    full_name       TEXT NOT NULL,
    email           TEXT,
    city            TEXT NOT NULL,            -- SCD2 tracked
    segment         TEXT NOT NULL,            -- SCD2 tracked
    valid_from      DATE NOT NULL,
    valid_to        DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_dim_customer_nk ON dw.dim_customer (customer_id, is_current);

CREATE TABLE dw.dim_product (
    product_key   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id    INT  NOT NULL,
    product_name  TEXT NOT NULL,
    category      TEXT NOT NULL,              -- SCD2 tracked (recategorizations matter)
    unit_price    NUMERIC(10,2) NOT NULL,     -- Type 1 (current list price)
    valid_from    DATE NOT NULL,
    valid_to      DATE NOT NULL DEFAULT '9999-12-31',
    is_current    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE dw.dim_store (
    store_key   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id    INT  NOT NULL,
    store_name  TEXT NOT NULL,
    region      TEXT NOT NULL                 -- Type 1 for FreshMart (regions are stable)
);

CREATE TABLE dw.fact_sales (
    sales_key     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key      INT    NOT NULL REFERENCES dw.dim_date (date_key),
    customer_key  BIGINT NOT NULL REFERENCES dw.dim_customer (customer_key),
    product_key   BIGINT NOT NULL REFERENCES dw.dim_product (product_key),
    store_key     BIGINT NOT NULL REFERENCES dw.dim_store (store_key),
    order_id      INT    NOT NULL,            -- degenerate dimension
    order_line_id INT    NOT NULL UNIQUE,     -- natural key of the grain → idempotency anchor
    quantity      INT    NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0),  -- price at time of sale
    line_amount   NUMERIC(12,2) NOT NULL CHECK (line_amount >= 0)
);
CREATE INDEX idx_fact_sales_date     ON dw.fact_sales (date_key);
CREATE INDEX idx_fact_sales_customer ON dw.fact_sales (customer_key);
CREATE INDEX idx_fact_sales_product  ON dw.fact_sales (product_key);
CREATE INDEX idx_fact_sales_store    ON dw.fact_sales (store_key);


-- Step 6 — Dry-run the model on paper
SELECT d.year, d.month, st.region, c.segment, SUM(f.line_amount) AS revenue
FROM dw.fact_sales f
JOIN dw.dim_date     d  ON d.date_key     = f.date_key
JOIN dw.dim_store    st ON st.store_key   = f.store_key
JOIN dw.dim_customer c  ON c.customer_key = f.customer_key
GROUP BY d.year, d.month, st.region, c.segment;

-- Alternate: current segment (not at time of sale)
SELECT d.year, d.month, st.region, cur.segment, SUM(f.line_amount) AS revenue
FROM dw.fact_sales f
JOIN dw.dim_date     d   ON d.date_key     = f.date_key
JOIN dw.dim_store    st  ON st.store_key   = f.store_key
JOIN dw.dim_customer hist ON hist.customer_key = f.customer_key
JOIN dw.dim_customer cur  ON cur.customer_id = hist.customer_id
                         AND cur.is_current = TRUE
GROUP BY d.year, d.month, st.region, cur.segment;