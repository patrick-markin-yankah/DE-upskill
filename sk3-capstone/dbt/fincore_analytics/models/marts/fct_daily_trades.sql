select
    order_id,
    portfolio_id,
    symbol,
    side,
    trade_date,
    quantity,
    price,
    currency,
    price_usd,
    close_price_usd,
    realized_pnl,
    traded_at
from {{ ref('stg_trades') }}
