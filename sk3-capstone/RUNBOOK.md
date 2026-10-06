# FinCore on-call runbook

Weekday pipeline `fincore_daily_pipeline`. It starts at 00:30 UTC and the risk team reads `analytics` before 06:30 UTC. One run at a time. The load deletes that date and inserts it again, so a clear does not double the rows.

| | |
|---|---|
| Airflow | http://localhost:8082 (`admin` / `admin`) |
| MinIO | http://localhost:9101 (`minioadmin` / `minioadmin123`) |
| Warehouse | `localhost:5434`, database `fincore`, user `fincore` |
| Slack | `#fincore-alerts` |
| Page copy | `alerts/out/page_YYYY-MM-DD.json` |

A log URL inside an alert uses port 8080. Open the same path on port 8082.

```text
wait_for_trades ──────── extract_trades ─────────┐
wait_for_market_data ─── extract_market_data ────┼─► sources_ready ─► spark_etl
wait_for_portfolio ───── extract_portfolio ──────┘        │
                                                          ▼
                                                   quality_gate
                                                    ├─ alert_quality_gate   (stop, published=false)
                                                    └─ load.load_warehouse
                                                         └─ dbt.dbt_run ─► dbt.dbt_test ─► record_run
                                                                              (SLA 6h)
```

Sensors poke every 10 minutes and give up after 4 hours. Spark retries 3 times, 15 minutes apart. A dbt test failure alerts and the task still exits 0. The load stays.

## Status

1. Airflow: `docker exec fincore-airflow-scheduler airflow dags list-runs -d fincore_daily_pipeline`
2. Scorecard in MinIO: bucket `fincore-processed`, key `metrics/dt=YYYY-MM-DD/quality_metrics.json`. Pass means reject rate under 0.02 and unpriced trades under 100. Unpriced trades are not part of the rate.
3. Warehouse:

```bash
psql -h localhost -p 5434 -U fincore -d fincore -c \
  "SELECT run_date, published, dbt_tests_passed, within_sla, reject_rate, pnl_unresolvable_count, duration_seconds FROM ops.pipeline_runs ORDER BY run_date DESC LIMIT 5;"
```

`published` true means that date was loaded. Render `monitoring/dashboard.html` with `python /opt/airflow/monitoring/render_dashboard.py` inside the scheduler when you want the 30-day charts.

## Market-data sensor timed out

Slack says `Missing source: market_data`. The copy is `alerts/out/YYYY-MM-DD_wait_for_market_data.json`.

Confirm `market_data/dt=YYYY-MM-DD/` in bucket `fincore-raw` has no `equities.csv` and no `fx.csv`. Leave the previous day's prices where they are. A missing close is a dead letter. Generate the date, or drop the real file in that prefix, then clear the date (command below). Spark does not start while the market extract is failed. Trades and portfolio extracts may already have succeeded if those files were present.

## Spark ran out of memory

The `spark_etl` log shows a driver `OutOfMemoryError`. Spark runs inside the scheduler. Memory is `spark.driver.memory` in `jobs/spark_common.py`, currently `2g`. Raise it (for example to `4g`), then clear `spark_etl` and everything after it:

```bash
docker exec fincore-airflow-scheduler airflow tasks clear fincore_daily_pipeline \
  -s YYYY-MM-DD -e YYYY-MM-DD -t '^spark_etl$' -d -y
```

The rewrite overwrites that date's Parquet and replaces that date in Postgres.

## Singular dbt test failed

`alerts/out/YYYY-MM-DD_dbt_test.json` says `dbt tests failed (advisory)` and that the data was not rolled back. The DAG stays green. `ops.pipeline_runs.dbt_tests_passed` is false and `published` is true. `agg_portfolio_pnl.total_pnl` does not match the sum of `fct_daily_trades.realized_pnl` for a portfolio and date.

```bash
psql -h localhost -p 5434 -U fincore -d fincore -c \
  "SELECT portfolio_id, pnl_date, total_pnl FROM analytics.agg_portfolio_pnl WHERE pnl_date = 'YYYY-MM-DD'
   EXCEPT
   SELECT portfolio_id, trade_date, sum(realized_pnl) FROM analytics.fct_daily_trades WHERE trade_date = 'YYYY-MM-DD' GROUP BY 1, 2;"
```

Fix the Spark job or the mart, then clear from `spark_etl` downward with the command in the memory section. The load replaces that date. dbt rebuilds the tables.

## Load failed with an S3 permissions error

The `load.load_warehouse` log shows boto3 `AccessDenied` against MinIO. That is the local form of a Redshift `COPY` IAM failure. The loader reads Parquet and inserts it.

Check `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` on the scheduler, and the Airflow connection `minio_s3` (endpoint `http://minio:9000`). Recreate the buckets if they are missing:

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/setup_buckets.py
```

Then clear the load and what follows it:

```bash
docker exec fincore-airflow-scheduler airflow tasks clear fincore_daily_pipeline \
  -s YYYY-MM-DD -e YYYY-MM-DD -t '^load\.load_warehouse$' -d -y
```

## Re-run one date

```bash
docker exec fincore-airflow-scheduler airflow tasks clear fincore_daily_pipeline \
  -s YYYY-MM-DD -e YYYY-MM-DD -y
```

Both dates are that day, so another day's run is left as it is. `-y` skips the prompt. The loader deletes `raw.trades` by `trade_date`, `raw.market_data` by `price_date`, and `raw.portfolio_pnl` by `pnl_date`, then inserts that date again. `order_id` stays unique. `loaded_at` changes.

A logical date before the DAG start (`2026-09-21`) creates a run with no tasks. A logical date that has not arrived stays queued. Mark that run failed. Only one run can be active, and a date with no files makes the sensors wait 4 hours.

## Escalation and the 6:30 deadline

| Role | Who |
|---|---|
| Primary on call | (name, phone) |
| Secondary | (name, phone) |
| Risk team | (name) — they read `analytics` before 06:30 UTC |

An SLA miss has already posted `PAGE. Pipeline missed the 6-hour SLA` to `#fincore-alerts` and written `alerts/out/page_YYYY-MM-DD.json`. Slack copies are also on disk when the webhook is down. Read the page, then decide which clock failed:

- **Gate.** `published` is false and `alerts/out/YYYY-MM-DD_quality_gate.json` has the reject rate and the unpriced count. Leave that date unpublished. Fix the file or the job, then clear from `spark_etl` down. The branch loads only when both limits pass.
- **Sensor.** The page is a missing source. Follow the market-data section (or the same steps for trades or portfolio).
- **Clock.** `within_sla` on the ops row is the run's own duration against 6 hours. Airflow's page uses the logical date. A manual run of an old date writes a page file even when the job took a minute. If `within_sla` is true and the run is green, the page is that clock. If the run is still going at 06:30, call the secondary and tell risk the mart is late.

To practice the page without waiting 6 hours, change `sla=timedelta(hours=6)` on `record_run` in `dags/fincore_daily_pipeline.py` to `sla=timedelta(minutes=1)`, trigger a date, then put `hours=6` back.
