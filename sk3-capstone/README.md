# FinCore daily pipeline

Overnight trade, price, and portfolio pipeline for the SK-03 capstone. The local platform, generator, Spark job, warehouse load, dbt project, Airflow DAG, dashboard, and runbook are in place.

| Doc | What it is |
|---|---|
| [`SK-03_Capstone_Project.md`](SK-03_Capstone_Project.md) | Assignment brief |
| [`explanation.md`](explanation.md) | Plain-language walkthrough |
| [`PLAN.md`](PLAN.md) | Build plan |
| [`commands.md`](commands.md) | Commands this checkout runs |
| [`stages.md`](stages.md) | What each build stage does, and how the code for it works |
| [`RUNBOOK.md`](RUNBOOK.md) | On-call page: status, four incidents, clear one date |

## Run order

From `sk3-capstone/`, with the stack up:

1. `python /opt/airflow/jobs/setup_buckets.py` inside the scheduler, once.
2. Optional: set `SLACK_WEBHOOK_URL` and recreate `airflow-init`, then `alerts.py --test`.
3. `generate_sources.py YYYY-MM-DD` with the counts you want. The files must exist before the DAG runs.
4. Unpause `fincore_daily_pipeline` and trigger that date. The DAG runs Spark, the quality gate, the load, and dbt.
5. `render_dashboard.py` writes `monitoring/dashboard.html`.

Each command is in [`commands.md`](commands.md). Incidents are in [`RUNBOOK.md`](RUNBOOK.md).

## Start and stop

From `sk3-capstone/`:

```bash
docker compose up -d
docker compose ps
docker compose down          # keeps data
docker compose down -v       # deletes MinIO, Airflow, and warehouse data
```

The first `up` builds the Airflow image (Java, PySpark, dbt, Slack provider). That takes several minutes.

## Where to look

| Service | On your Mac | Login |
|---|---|---|
| Airflow | http://localhost:8082 | `admin` / `admin` |
| MinIO console | http://localhost:9101 | `minioadmin` / `minioadmin123` |
| MinIO API | http://localhost:9100 | same user |
| Warehouse | `localhost:5434`, database `fincore` | `fincore` / `fincore` |

Inside the Compose network the hostnames are `minio:9000` and `warehouse:5432`. dbt and Spark jobs use those, not the Mac ports.

These ports are shifted from the UrbanGear lab so both stacks can run at once.

## Buckets

After the scheduler is up:

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/setup_buckets.py
```

That creates `fincore-raw`, `fincore-processed`, and `fincore-rejected`. Running it again is safe.

## Slack

Copy `.env.example` to `.env` if you do not already have one, and set `SLACK_WEBHOOK_URL` to an incoming webhook. Then recreate init so Airflow stores the connection:

```bash
docker compose up -d --force-recreate --no-deps airflow-init
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/alerts.py --test
```

The test posts `FinCore Slack is connected` and nothing else. Leave the variable blank to boot the stack without Slack. Do not commit `.env`.

## Generator

One trading day of raw files lands in MinIO. Counts are arguments, not a fixed volume. See [`commands.md`](commands.md) for the full form. A small day:

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/generate_sources.py 2026-09-21
```

The brief-sized day (500,000 trades, 50,000 prices, 8,000 positions):

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/generate_sources.py 2026-09-21 --trades 500000 --market-rows 50000 --positions 8000
```

## Spark job

After that date's raw files are in MinIO:

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/etl_job.py 2026-09-21
```

This overwrites the clean trades, portfolio P&L, prices, rejects, and the scorecard for that date. Running it again replaces those files. See [`commands.md`](commands.md).

## Warehouse load

After that date's Parquet exists:

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/jobs/load_warehouse.py 2026-09-21
```

This deletes that date from `raw.trades`, `raw.market_data`, and `raw.portfolio_pnl`, then inserts it again. Money columns are `NUMERIC(18, 6)`. Other dates in those tables are left alone. Running it again leaves the same row counts. From your Mac, query with `psql -h localhost -p 5434 -U fincore -d fincore`.

## dbt

After that date is in Postgres. The first command installs `dbt_utils`. The second builds the views, tables, seed, and tests:

```bash
docker exec -w /opt/airflow/dbt/fincore_analytics fincore-airflow-scheduler \
  dbt deps --profiles-dir /opt/airflow/dbt
docker exec -w /opt/airflow/dbt/fincore_analytics fincore-airflow-scheduler \
  dbt build --profiles-dir /opt/airflow/dbt
```

Models land in schema `analytics`. See [`commands.md`](commands.md).

## DAG

The weekday DAG is `fincore_daily_pipeline` (00:30 UTC, SLA 6 hours). It stays paused until you unpause it. Trigger the date whose raw files are already in MinIO:

```bash
docker exec fincore-airflow-scheduler airflow dags unpause fincore_daily_pipeline
docker exec fincore-airflow-scheduler airflow dags trigger fincore_daily_pipeline --exec-date 2026-09-21
```

Unpausing also opens the latest weekday that has already passed. If that date has no files, mark that run failed before the trigger above. Only one run is active at a time, and a missing file makes the sensors wait 4 hours.

To run the same date again:

```bash
docker exec fincore-airflow-scheduler airflow tasks clear fincore_daily_pipeline \
  -s 2026-09-21 -e 2026-09-21 -y
```

That clears Monday only. The second load replaces that date, so the row counts stay the same. The graph, the quality gate, and the ops row are in [`commands.md`](commands.md) and [`stages.md`](stages.md).

## Dashboard

```bash
docker exec fincore-airflow-scheduler python /opt/airflow/monitoring/render_dashboard.py
```

Writes `monitoring/dashboard.html` from `ops.pipeline_runs`: duration, record counts, rejection rate, SLA, and dbt pass rate for the last 30 days. Open that file in a browser.

## Assumptions

- Trade, price, and position counts are arguments to the generator. A small day and the brief-sized day use the same jobs.
- Money is `NUMERIC(18, 6)` from Spark through Postgres.
- A trade with no closing price is counted on its own. It is not part of the 2% reject rate. Both limits must pass or the load is skipped.
- A missing close stays missing. The next run does not fill it from the previous day.
- The local load deletes one date and inserts it. In production the same failure mode is a Redshift `COPY` that cannot read S3. See [`RUNBOOK.md`](RUNBOOK.md).
- A failing dbt test alerts and leaves the loaded rows in place.
