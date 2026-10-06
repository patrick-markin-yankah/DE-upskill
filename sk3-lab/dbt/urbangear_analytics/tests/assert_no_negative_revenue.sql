-- Rows returned = failures.
select *
from {{ ref('fct_daily_product_sales') }}
where revenue < 0