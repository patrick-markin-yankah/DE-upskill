"""Upsert one row in ops.pipeline_runs for a DAG date.

The quality-gate failure path records published=false.
The success path records published=true after dbt.
A second run for the same date replaces the row.
"""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import psycopg2
from botocore.exceptions import ClientError

PROCESSED = "fincore-processed"
SLA_SECONDS = 6 * 60 * 60

DDL = """
CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_date DATE NOT NULL,
    dag_id TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    total_trade_count BIGINT,
    clean_trade_count BIGINT,
    rejected_trade_count BIGINT,
    reject_rate NUMERIC(18, 6),
    pnl_unresolvable_count BIGINT,
    total_realized_pnl_usd NUMERIC(18, 6),
    within_sla BOOLEAN,
    dbt_tests_passed BOOLEAN,
    published BOOLEAN,
    PRIMARY KEY (run_date, dag_id)
)
"""


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


def read_metrics(run_date: str) -> dict | None:
    key = f"metrics/dt={run_date}/quality_metrics.json"
    try:
        body = s3_client().get_object(Bucket=PROCESSED, Key=key)["Body"].read()
    except ClientError as exc:
        print(f"[record_run] no metrics at s3://{PROCESSED}/{key}: {exc}")
        return None
    return json.loads(body)


def gate_passes(metrics: dict) -> bool:
    rate = Decimal(str(metrics["reject_rate"]))
    unresolvable = int(metrics["pnl_unresolvable_count"])
    return rate < Decimal("0.02") and unresolvable < 100


def _counts(metrics: dict | None) -> dict:
    if not metrics:
        return {
            "total_trade_count": None,
            "clean_trade_count": None,
            "rejected_trade_count": None,
            "reject_rate": None,
            "pnl_unresolvable_count": None,
            "total_realized_pnl_usd": None,
        }
    rejected = sum(int(value) for value in metrics["rejection_count_by_rule"].values())
    return {
        "total_trade_count": int(metrics["total_trade_count"]),
        "clean_trade_count": int(metrics["clean_trade_count"]),
        "rejected_trade_count": rejected,
        "reject_rate": Decimal(str(metrics["reject_rate"])),
        "pnl_unresolvable_count": int(metrics["pnl_unresolvable_count"]),
        "total_realized_pnl_usd": Decimal(metrics["total_realized_pnl_usd"]),
    }


def upsert(run_date: str, dag_id: str, started_at, finished_at, published: bool, dbt_tests_passed: bool, metrics: dict | None) -> None:
    duration = int((finished_at - started_at).total_seconds())
    within_sla = duration < SLA_SECONDS
    counts = _counts(metrics)
    conn = warehouse_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")
                cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
                cur.execute(DDL)
                cur.execute(
                    """
                    INSERT INTO ops.pipeline_runs (
                        run_date, dag_id, started_at, finished_at, duration_seconds,
                        total_trade_count, clean_trade_count, rejected_trade_count,
                        reject_rate, pnl_unresolvable_count, total_realized_pnl_usd,
                        within_sla, dbt_tests_passed, published
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                    ON CONFLICT (run_date, dag_id) DO UPDATE SET
                        started_at = EXCLUDED.started_at,
                        finished_at = EXCLUDED.finished_at,
                        duration_seconds = EXCLUDED.duration_seconds,
                        total_trade_count = EXCLUDED.total_trade_count,
                        clean_trade_count = EXCLUDED.clean_trade_count,
                        rejected_trade_count = EXCLUDED.rejected_trade_count,
                        reject_rate = EXCLUDED.reject_rate,
                        pnl_unresolvable_count = EXCLUDED.pnl_unresolvable_count,
                        total_realized_pnl_usd = EXCLUDED.total_realized_pnl_usd,
                        within_sla = EXCLUDED.within_sla,
                        dbt_tests_passed = EXCLUDED.dbt_tests_passed,
                        published = EXCLUDED.published
                    """,
                    (
                        run_date,
                        dag_id,
                        started_at,
                        finished_at,
                        duration,
                        counts["total_trade_count"],
                        counts["clean_trade_count"],
                        counts["rejected_trade_count"],
                        counts["reject_rate"],
                        counts["pnl_unresolvable_count"],
                        counts["total_realized_pnl_usd"],
                        within_sla,
                        dbt_tests_passed,
                        published,
                    ),
                )
        print(
            f"[record_run] date={run_date} published={published} "
            f"dbt_tests_passed={dbt_tests_passed} within_sla={within_sla} "
            f"duration_seconds={duration}"
        )
    finally:
        conn.close()


def record_from_context(context, published: bool, dbt_tests_passed: bool) -> None:
    started = context["dag_run"].start_date
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    finished = datetime.now(timezone.utc)
    upsert(
        context["ds"],
        context["dag"].dag_id,
        started,
        finished,
        published,
        dbt_tests_passed,
        read_metrics(context["ds"]),
    )
