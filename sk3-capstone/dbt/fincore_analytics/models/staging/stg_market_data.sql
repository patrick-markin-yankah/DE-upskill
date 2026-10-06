with source as (
    select * from {{ source('raw', 'market_data') }}
),

renamed as (
    select
        symbol,
        lower(asset_class) as asset_class,
        currency,
        cast(close_price as numeric(18, 6)) as close_price,
        cast(fx_to_usd as numeric(18, 6)) as fx_to_usd,
        cast(close_price_usd as numeric(18, 6)) as close_price_usd,
        cast(price_date as date) as price_date,
        cast(loaded_at as timestamptz) as loaded_at
    from source
)

select * from renamed
