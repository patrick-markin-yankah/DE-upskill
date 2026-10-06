-- Rows returned = failures.
select *
from "warehouse"."analytics"."fct_daily_product_sales"
where revenue < 0