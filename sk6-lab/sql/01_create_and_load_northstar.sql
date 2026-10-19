-- NorthStar Retail source database (OLTP-style) for SK-06
-- Run inside the container:  psql -U postgres -d northstar -f /sql/01_create_and_load_northstar.sql
-- Safe to re-run: it drops and recreates the three schemas.
\set ON_ERROR_STOP on

DROP SCHEMA IF EXISTS sales CASCADE;
DROP SCHEMA IF EXISTS products CASCADE;
DROP SCHEMA IF EXISTS finance CASCADE;
CREATE SCHEMA sales;
CREATE SCHEMA products;
CREATE SCHEMA finance;

-- ---------- geography ----------
CREATE TABLE sales.regions (
    region_id    INT PRIMARY KEY,
    region_name  TEXT NOT NULL UNIQUE
);
CREATE TABLE sales.districts (
    district_id    INT PRIMARY KEY,
    district_name  TEXT NOT NULL,
    region_id      INT NOT NULL REFERENCES sales.regions(region_id)
);
CREATE TABLE sales.stores (
    store_id     INT PRIMARY KEY,
    store_name   TEXT NOT NULL,
    district_id  INT NOT NULL REFERENCES sales.districts(district_id),
    city         TEXT NOT NULL,
    state        CHAR(2) NOT NULL,
    latitude     NUMERIC(9,6),
    longitude    NUMERIC(9,6),
    open_date    DATE
);

-- ---------- product hierarchy ----------
CREATE TABLE products.categories (
    category_id    INT PRIMARY KEY,
    category_name  TEXT NOT NULL UNIQUE
);
CREATE TABLE products.subcategories (
    subcategory_id    INT PRIMARY KEY,
    subcategory_name  TEXT NOT NULL,
    category_id       INT NOT NULL REFERENCES products.categories(category_id)
);
CREATE TABLE products.products (
    product_id      INT PRIMARY KEY,
    product_name    TEXT NOT NULL,
    subcategory_id  INT NOT NULL REFERENCES products.subcategories(subcategory_id),
    brand           TEXT NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    list_price      NUMERIC(10,2) NOT NULL
);

-- ---------- customers and promotions ----------
CREATE TABLE sales.customers (
    customer_id        INT PRIMARY KEY,
    first_name         TEXT NOT NULL,
    last_name          TEXT NOT NULL,
    email              TEXT NOT NULL,
    customer_segment   TEXT NOT NULL,
    registration_date  DATE NOT NULL,
    city               TEXT,
    state              CHAR(2)
);
CREATE TABLE sales.promotions (
    promotion_id    INT PRIMARY KEY,
    promotion_name  TEXT NOT NULL,
    promotion_type  TEXT NOT NULL,
    discount_pct    NUMERIC(4,2) NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL
);

-- ---------- transactions ----------
CREATE TABLE sales.orders (
    order_id       BIGINT PRIMARY KEY,
    order_date     DATE NOT NULL,
    ship_date      DATE,                 -- NULL = not shipped (cancelled)
    customer_id    INT NOT NULL REFERENCES sales.customers(customer_id),
    is_returned    SMALLINT NOT NULL,    -- 1 = order was returned
    created_by     TEXT,                 -- audit column (not needed for BI)
    source_system  TEXT                  -- pipeline column (not needed for BI)
);
CREATE TABLE sales.order_lines (
    order_line_id    BIGINT PRIMARY KEY,
    order_id         BIGINT NOT NULL REFERENCES sales.orders(order_id),
    line_number      INT NOT NULL,
    product_id       INT NOT NULL REFERENCES products.products(product_id),
    store_id         INT NOT NULL REFERENCES sales.stores(store_id),
    promotion_id     INT NOT NULL REFERENCES sales.promotions(promotion_id),
    quantity         INT NOT NULL,
    unit_price       NUMERIC(10,2) NOT NULL,
    discount_amount  NUMERIC(10,2) NOT NULL
);

-- ---------- monthly targets (one row per store per month) ----------
CREATE TABLE finance.revenue_targets (
    store_id        INT NOT NULL REFERENCES sales.stores(store_id),
    target_month    DATE NOT NULL,       -- always the 1st of the month
    revenue_target  NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (store_id, target_month)
);

-- ---------- load the CSV files (mounted at /data in the container) ----------
COPY sales.regions            FROM '/data/regions.csv'         WITH (FORMAT csv, HEADER true);
COPY sales.districts          FROM '/data/districts.csv'       WITH (FORMAT csv, HEADER true);
COPY sales.stores             FROM '/data/stores.csv'          WITH (FORMAT csv, HEADER true);
COPY products.categories      FROM '/data/categories.csv'      WITH (FORMAT csv, HEADER true);
COPY products.subcategories   FROM '/data/subcategories.csv'   WITH (FORMAT csv, HEADER true);
COPY products.products        FROM '/data/products.csv'        WITH (FORMAT csv, HEADER true);
COPY sales.customers          FROM '/data/customers.csv'       WITH (FORMAT csv, HEADER true);
COPY sales.promotions         FROM '/data/promotions.csv'      WITH (FORMAT csv, HEADER true);
COPY sales.orders             FROM '/data/orders.csv'          WITH (FORMAT csv, HEADER true);
COPY sales.order_lines        FROM '/data/order_lines.csv'     WITH (FORMAT csv, HEADER true);
COPY finance.revenue_targets  FROM '/data/revenue_targets.csv' WITH (FORMAT csv, HEADER true);

CREATE INDEX ix_order_lines_order ON sales.order_lines(order_id);
CREATE INDEX ix_orders_order_date ON sales.orders(order_date);
ANALYZE;

-- ---------- row-count check ----------
SELECT 'sales.regions' AS table_name, COUNT(*) AS row_count FROM sales.regions
UNION ALL SELECT 'sales.districts',          COUNT(*) FROM sales.districts
UNION ALL SELECT 'sales.stores',             COUNT(*) FROM sales.stores
UNION ALL SELECT 'products.categories',      COUNT(*) FROM products.categories
UNION ALL SELECT 'products.subcategories',   COUNT(*) FROM products.subcategories
UNION ALL SELECT 'products.products',        COUNT(*) FROM products.products
UNION ALL SELECT 'sales.customers',          COUNT(*) FROM sales.customers
UNION ALL SELECT 'sales.promotions',         COUNT(*) FROM sales.promotions
UNION ALL SELECT 'sales.orders',             COUNT(*) FROM sales.orders
UNION ALL SELECT 'sales.order_lines',        COUNT(*) FROM sales.order_lines
UNION ALL SELECT 'finance.revenue_targets',  COUNT(*) FROM finance.revenue_targets;