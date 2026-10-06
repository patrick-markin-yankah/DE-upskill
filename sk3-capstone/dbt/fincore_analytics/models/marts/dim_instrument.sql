with prices as (
    select
        symbol,
        min(asset_class) as asset_class,
        min(currency) as currency
    from {{ ref('stg_market_data') }}
    group by symbol
),

meta as (
    select * from {{ ref('instrument_metadata') }}
)

select
    prices.symbol,
    coalesce(meta.asset_class, prices.asset_class) as asset_class,
    prices.currency,
    nullif(meta.instrument_name, '') as instrument_name,
    nullif(meta.exchange, '') as exchange
from prices
left join meta
    on prices.symbol = meta.symbol
