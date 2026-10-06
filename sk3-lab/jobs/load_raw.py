"""Load Lab 05 processed Parquet from MinIO into warehouse.raw.orders."""
from io import BytesIO

import boto3
import pandas as pd
from sqlalchemy import create_engine, text

s3 = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin123",
)

frames = []
resp = s3.list_objects_v2(Bucket="urbangear-processed", Prefix="processed/orders/")
for obj in resp.get("Contents", []):
    key = obj["Key"]
    if not key.endswith(".parquet"):
        continue
    body = s3.get_object(Bucket="urbangear-processed", Key=key)["Body"].read()
    part = pd.read_parquet(BytesIO(body))
    # Spark wrote to .../date=YYYY-MM-DD/; that date is not always a column
    if "date=" in key:
        part["order_date"] = key.split("date=")[1].split("/")[0]
    frames.append(part)

if not frames:
    raise SystemExit("no Parquet under urbangear-processed/processed/orders/")

df = pd.concat(frames, ignore_index=True)

engine = create_engine("postgresql://dwh_user:dwh_pass@warehouse:5432/warehouse")
with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
    table_exists = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw' AND table_name = 'orders'
            )
            """
        )
    ).scalar()
    # Wipe rows, not the relation. if_exists="replace" DROP TABLEs, and Postgres
    # refuses that once dbt's analytics.stg_orders view depends on raw.orders.
    if table_exists:
        conn.execute(text("TRUNCATE TABLE raw.orders"))
    df.to_sql("orders", conn, schema="raw", if_exists="append", index=False)
print(f"Loaded {len(df):,} rows into raw.orders")