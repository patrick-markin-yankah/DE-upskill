
  
    

  create  table "warehouse"."analytics"."fct_daily_product_sales__dbt_tmp"
  
  
    as
  
  (
    

with orders as (
    select * from "warehouse"."analytics"."stg_orders"
)

select
    order_date,
    product_id,
    product_name,
    count(distinct order_id) as orders,
    sum(quantity)            as units_sold,
    sum(line_amount)         as revenue
from orders
group by 1, 2, 3
  );
  