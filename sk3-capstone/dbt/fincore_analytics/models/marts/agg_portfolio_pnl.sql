select
    portfolio_id,
    pnl_date,
    total_pnl,
    position_count,
    total_market_value_usd
from {{ ref('stg_portfolio_pnl') }}
