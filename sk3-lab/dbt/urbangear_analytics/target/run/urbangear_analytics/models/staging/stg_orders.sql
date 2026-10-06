
  create view "warehouse"."analytics"."stg_orders__dbt_tmp"
    
    
  as (
    with source as (
    select * from "warehouse"."raw"."orders"
),

renamed as (
    select
        order_id,
        product_id,
        product_name,
        customer_email,
        cast(quantity as integer)         as quantity,
        cast(unit_price as numeric(10,2)) as unit_price,
        cast(amount as numeric(10,2))     as line_amount,
        cast(order_ts as timestamp)       as ordered_at,
        cast(order_date as date)          as order_date
    from source
)

select * from renamed
  );