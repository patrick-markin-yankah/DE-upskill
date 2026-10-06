-- Rows returned are failures. Numeric inequality is exact. No tolerance.
with trade_sums as (
    select
        portfolio_id,
        trade_date as pnl_date,
        sum(realized_pnl) as trade_pnl
    from {{ ref('fct_daily_trades') }}
    group by portfolio_id, trade_date
),

compared as (
    select
        coalesce(agg.portfolio_id, trade_sums.portfolio_id) as portfolio_id,
        coalesce(agg.pnl_date, trade_sums.pnl_date) as pnl_date,
        agg.total_pnl,
        trade_sums.trade_pnl
    from {{ ref('agg_portfolio_pnl') }} as agg
    full outer join trade_sums
        on agg.portfolio_id = trade_sums.portfolio_id
        and agg.pnl_date = trade_sums.pnl_date
)

select *
from compared
where coalesce(total_pnl, 0) <> coalesce(trade_pnl, 0)
