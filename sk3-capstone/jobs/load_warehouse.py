"""Load one FinCore date from Parquet into Postgres.

Usage: python load_warehouse.py YYYY-MM-DD

Deletes that date from raw.trades, raw.market_data, and raw.portfolio_pnl,
then inserts the Parquet for that date. A second run replaces the date.
It does not truncate the tables, so other dates stay.
"""
import csv
import io
import os
import sys
from datetime import date, datetime
from decimal import Decimal

import boto3
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError

PROCESSED = "fincore-processed"
MONEY = "NUMERIC(18, 6)"

DATASETS = (
    {
        "table": "raw.trades",
        "prefix": "processed/trades",
        "date_column": "trade_date",
        "columns": [
            "order_id",
            "portfolio_id",
            "symbol",
            "side",
            "quantity",
            "price",
            "currency",
            "transact_time",
            "trade_date",
            "close_price_usd",
            "price_usd",
            "realized_pnl",
        ],
        "money": ["quantity", "price", "close_price_usd", "price_usd", "realized_pnl"],
        "ddl": f"""
            CREATE TABLE IF NOT EXISTS raw.trades (
                order_id TEXT,
                portfolio_id TEXT,
                symbol TEXT,
                side TEXT,
                quantity {MONEY},
                price {MONEY},
                currency TEXT,
                transact_time TIMESTAMP,
                trade_date DATE,
                close_price_usd {MONEY},
                price_usd {MONEY},
                realized_pnl {MONEY},
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """,
    },
    {
        "table": "raw.market_data",
        "prefix": "processed/market_data",
        "date_column": "price_date",
        "columns": [
            "symbol",
            "asset_class",
            "close_price",
            "currency",
            "price_date",
            "fx_to_usd",
            "close_price_usd",
        ],
        "money": ["close_price", "fx_to_usd", "close_price_usd"],
        "ddl": f"""
            CREATE TABLE IF NOT EXISTS raw.market_data (
                symbol TEXT,
                asset_class TEXT,
                close_price {MONEY},
                currency TEXT,
                price_date DATE,
                fx_to_usd {MONEY},
                close_price_usd {MONEY},
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """,
    },
    {
        "table": "raw.portfolio_pnl",
        "prefix": "processed/portfolio_pnl",
        "date_column": "pnl_date",
        "columns": [
            "portfolio_id",
            "pnl_date",
            "total_pnl",
            "position_count",
            "total_market_value_usd",
            "max_gross_exposure_usd",
            "max_position_pct",
        ],
        "money": [
            "total_pnl",
            "total_market_value_usd",
            "max_gross_exposure_usd",
            "max_position_pct",
        ],
        "ddl": f"""
            CREATE TABLE IF NOT EXISTS raw.portfolio_pnl (
                portfolio_id TEXT,
                pnl_date DATE,
                total_pnl {MONEY},
                position_count BIGINT,
                total_market_value_usd {MONEY},
                max_gross_exposure_usd {MONEY},
                max_position_pct {MONEY},
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """,
    },
)


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


def warehouse_conn():
    return psycopg2.connect(
        host=os.environ["WAREHOUSE_HOST"],
        port=os.environ["WAREHOUSE_PORT"],
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
    )


def parquet_table(s3, prefix: str) -> pa.Table:
    keys = []
    token = None
    try:
        while True:
            kwargs = {"Bucket": PROCESSED, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                if obj["Key"].endswith(".parquet"):
                    keys.append(obj["Key"])
            if not resp.get("IsTruncated"):
                break
            token = resp["NextContinuationToken"]
    except ClientError as exc:
        raise SystemExit(f"could not list s3://{PROCESSED}/{prefix}: {exc}") from exc
    if not keys:
        raise SystemExit(f"NO INPUT at s3://{PROCESSED}/{prefix} — refusing to load an empty date")
    tables = []
    for key in keys:
        body = s3.get_object(Bucket=PROCESSED, Key=key)["Body"].read()
        tables.append(pq.read_table(io.BytesIO(body)))
    return pa.concat_tables(tables)


def cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def copy_table(cur, table: str, columns: list[str], rows: pa.Table) -> int:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for record in rows.select(columns).to_pylist():
        writer.writerow([cell(record[name]) for name in columns])
    buf.seek(0)
    column_list = ", ".join(columns)
    cur.copy_expert(
        f"COPY {table} ({column_list}) FROM STDIN WITH (FORMAT csv, NULL '')",
        buf,
    )
    return rows.num_rows


def assert_money_types(cur, table: str, columns: list[str]) -> None:
    cur.execute(
        """
        SELECT column_name, data_type, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'raw'
          AND table_name = %s
          AND column_name = ANY(%s)
        """,
        (table.split(".", 1)[1], columns),
    )
    found = {row[0]: row for row in cur.fetchall()}
    for name in columns:
        row = found.get(name)
        if row is None or row[1] != "numeric" or row[2] != 18 or row[3] != 6:
            raise SystemExit(f"{table}.{name} is not NUMERIC(18, 6): {row}")


def assert_partition_date(table: pa.Table, column: str, run_date: date) -> None:
    values = {value for value in table.column(column).to_pylist()}
    if values != {run_date}:
        raise SystemExit(f"{column} in Parquet is {sorted(map(str, values))}, expected {run_date}")


def main(run_date: str) -> None:
    try:
        parsed = datetime.strptime(run_date, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("usage: load_warehouse.py YYYY-MM-DD")

    s3 = s3_client()
    frames = []
    for spec in DATASETS:
        frame = parquet_table(s3, f"{spec['prefix']}/dt={run_date}/")
        assert_partition_date(frame, spec["date_column"], parsed)
        frames.append(frame)

    conn = warehouse_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")
                cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
                cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
                counts = []
                for spec, frame in zip(DATASETS, frames):
                    cur.execute(spec["ddl"])
                    assert_money_types(cur, spec["table"], spec["money"])
                    cur.execute(
                        f"DELETE FROM {spec['table']} WHERE {spec['date_column']} = %s",
                        (parsed,),
                    )
                    loaded = copy_table(cur, spec["table"], spec["columns"], frame)
                    counts.append((spec["table"], loaded))

                cur.execute(
                    """
                    SELECT close_price, fx_to_usd, close_price_usd
                    FROM raw.market_data
                    WHERE symbol = 'VOD' AND price_date = %s
                    """,
                    (parsed,),
                )
                vod = cur.fetchone()
                if vod is None or vod[0] * vod[1] != vod[2]:
                    raise SystemExit(f"GBP close did not stay exact in Postgres: {vod}")
        print(
            f"[load_warehouse] date={run_date} "
            + " ".join(f"{name.split('.')[1]}={count}" for name, count in counts)
        )
        print(
            "[load_warehouse] GBP check "
            f"VOD close={vod[0]} fx={vod[1]} close_usd={vod[2]}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: load_warehouse.py YYYY-MM-DD")
    main(sys.argv[1])
