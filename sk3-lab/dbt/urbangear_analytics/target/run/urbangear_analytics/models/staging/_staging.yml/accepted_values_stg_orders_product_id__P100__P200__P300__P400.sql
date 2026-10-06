select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    

with all_values as (

    select
        product_id as value_field,
        count(*) as n_records

    from "warehouse"."analytics"."stg_orders"
    group by product_id

)

select *
from all_values
where value_field not in (
    'P100','P200','P300','P400'
)



      
    ) dbt_internal_test