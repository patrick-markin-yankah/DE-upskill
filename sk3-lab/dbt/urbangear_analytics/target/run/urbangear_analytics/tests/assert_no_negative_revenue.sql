select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      -- Rows returned = failures.
select *
from "warehouse"."analytics"."fct_daily_product_sales"
where revenue < 0
      
    ) dbt_internal_test