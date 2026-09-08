# Notes

## Fanout

**What it is:** Join fanout is when a join multiplies rows because one side matches many rows on the other (e.g. one order → many order lines). Aggregates like `SUM` then count those values more than once and overstate totals. The intentional bug in `02_joins_windows.sql` (joining `order_lines` twice to the same order) is a classic fanout.

**How to detect it:**
- Compare grain: if the result has more rows than the “left” grain you expected (e.g. more rows than orders), something multiplied.
- Spot-check totals: `SUM(line_amount)` after the join vs `SUM(line_amount)` from `order_lines` alone (or with a correct filter) — a large mismatch usually means fanout.
- Use `COUNT(*)` vs `COUNT(DISTINCT key)` on the join key; if `COUNT(*)` ≫ `COUNT(DISTINCT order_id)`, rows were duplicated.
- Fix by aggregating to the join key first (one row per order), then joining — as in the `order_totals` CTE pattern.


## Design Decisions

- Business process: retail sales (order lines).
- Grain: one row per product line on a completed order.
- Dimensions: date, customer, product, store (+ degenerate: order_id).
- Facts: quantity, unit_price, line_amount.

## Monitoring (local)

Local monitoring is two SQL checks against `etl.run_audit`: (1) no successful `load_fact_sales` / `validate_staging_sales` in 26 hours, and (2) reject rate above 1%. In production a scheduler or observability tool simply runs them and emails on `true`.
