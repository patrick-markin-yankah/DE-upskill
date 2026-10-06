with source as (
    select * from {{ source('raw', 'portfolio_pnl') }}
),

renamed as (
    select
        portfolio_id,
        cast(pnl_date as date) as pnl_date,
        cast(total_pnl as numeric(18, 6)) as total_pnl,
        cast(position_count as bigint) as position_count,
        cast(total_market_value_usd as numeric(18, 6)) as total_market_value_usd,
        cast(max_gross_exposure_usd as numeric(18, 6)) as max_gross_exposure_usd,
        cast(max_position_pct as numeric(18, 6)) as max_position_pct,
        cast(loaded_at as timestamptz) as loaded_at
    from source
)

select * from renamed
