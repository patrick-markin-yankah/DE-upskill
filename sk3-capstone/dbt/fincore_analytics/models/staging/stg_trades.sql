with source as (
    select * from {{ source('raw', 'trades') }}
),

renamed as (
    select
        order_id,
        portfolio_id,
        symbol,
        side,
        currency,
        cast(quantity as numeric(18, 6)) as quantity,
        cast(price as numeric(18, 6)) as price,
        cast(price_usd as numeric(18, 6)) as price_usd,
        cast(close_price_usd as numeric(18, 6)) as close_price_usd,
        cast(realized_pnl as numeric(18, 6)) as realized_pnl,
        cast(transact_time as timestamp) as traded_at,
        cast(trade_date as date) as trade_date,
        cast(loaded_at as timestamptz) as loaded_at
    from source
)

select * from renamed
