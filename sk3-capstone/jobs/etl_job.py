"""Clean one FinCore day: FIX trades, prices, and portfolios.

Usage: python etl_job.py YYYY-MM-DD

Reads s3://fincore-raw/.../dt=<date>/ and overwrites that date's outputs.
A second run replaces the Parquet. It does not append.
"""
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, "/opt/airflow/jobs")

import boto3
from botocore.exceptions import ClientError
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    DecimalType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

from spark_common import get_spark

MONEY = DecimalType(18, 6)
RAW = "fincore-raw"
PROCESSED = "fincore-processed"
REJECTED = "fincore-rejected"
TRADE_RULES = (
    "malformed_line",
    "bad_side",
    "bad_quantity",
    "bad_price",
    "bad_timestamp",
)
REJECT_FIELDS = ["source", "reason", "raw_record", "order_id", "symbol", "portfolio_id"]


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


def require_prefix(s3, prefix: str) -> None:
    try:
        resp = s3.list_objects_v2(Bucket=RAW, Prefix=prefix, MaxKeys=1)
    except ClientError as exc:
        raise SystemExit(f"could not list s3://{RAW}/{prefix}: {exc}") from exc
    if resp.get("KeyCount", 0) == 0:
        raise SystemExit(f"NO INPUT at s3://{RAW}/{prefix} — refusing to write empty output")


def norm(col):
    return F.upper(F.trim(col))


def blank_to_null(col):
    text = F.trim(col)
    return F.when(text.isNull() | (F.length(text) == 0), F.lit(None)).otherwise(text)


def tag_value(col_name: str, tag: str):
    extracted = F.regexp_extract(F.col(col_name), rf"^{tag}=(.*)$", 1)
    return blank_to_null(extracted)


def money_text(value) -> str:
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"{value.quantize(Decimal('0.000001'))}"


def reject_frame(
    df: DataFrame,
    source: str,
    reason: str | F.Column = "reason",
    raw_record: str | F.Column = "raw_record",
    order_id: str | F.Column | None = None,
    symbol: str | F.Column | None = None,
    portfolio_id: str | F.Column | None = None,
) -> DataFrame:
    def col_or_null(value, name: str):
        if value is None:
            return F.lit(None).cast("string").alias(name)
        if isinstance(value, str):
            return F.col(value).cast("string").alias(name)
        return value.cast("string").alias(name)

    reason_col = F.col(reason) if isinstance(reason, str) else reason
    raw_col = F.col(raw_record) if isinstance(raw_record, str) else raw_record
    return df.select(
        F.lit(source).alias("source"),
        reason_col.cast("string").alias("reason"),
        raw_col.cast("string").alias("raw_record"),
        col_or_null(order_id, "order_id"),
        col_or_null(symbol, "symbol"),
        col_or_null(portfolio_id, "portfolio_id"),
    )


def read_trades(spark: SparkSession, run_date: str) -> DataFrame:
    fields = [StructField(f"f{i}", StringType(), True) for i in range(12)]
    fields.append(StructField("_corrupt_record", StringType(), True))
    raw = (
        spark.read
        .option("header", "false")
        .option("sep", "|")
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .schema(StructType(fields))
        .csv(f"s3a://{RAW}/trades/dt={run_date}/")
    )
    parsed = (
        raw
        .withColumn("order_id", tag_value("f3", "37"))
        .withColumn("portfolio_id", tag_value("f4", "1"))
        .withColumn("symbol_raw", tag_value("f5", "55"))
        .withColumn("side_code", tag_value("f6", "54"))
        .withColumn("quantity", tag_value("f7", "38").cast(MONEY))
        .withColumn("price", tag_value("f8", "6").cast(MONEY))
        .withColumn("currency", tag_value("f9", "15"))
        .withColumn(
            "transact_time",
            F.to_timestamp(tag_value("f10", "60"), "yyyyMMdd-HH:mm:ss"),
        )
        .withColumn(
            "raw_record",
            F.coalesce(F.col("_corrupt_record"), F.concat_ws("|", *[F.col(f"f{i}") for i in range(12)])),
        )
    )
    reason = (
        F.when(F.col("_corrupt_record").isNotNull(), F.lit("malformed_line"))
        .when(
            F.col("order_id").isNull()
            | F.col("portfolio_id").isNull()
            | F.col("symbol_raw").isNull()
            | F.col("currency").isNull(),
            F.lit("malformed_line"),
        )
        .when(~F.col("side_code").isin("1", "2"), F.lit("bad_side"))
        .when(F.col("quantity").isNull() | (F.col("quantity") <= 0), F.lit("bad_quantity"))
        .when(F.col("price").isNull() | (F.col("price") <= 0), F.lit("bad_price"))
        .when(F.col("transact_time").isNull(), F.lit("bad_timestamp"))
    )
    return (
        parsed
        .withColumn("reason", reason)
        .withColumn("symbol", norm(F.col("symbol_raw")))
        .withColumn(
            "side",
            F.when(F.col("side_code") == "1", F.lit("BUY")).when(F.col("side_code") == "2", F.lit("SELL")),
        )
        .withColumn(
            "side_multiplier",
            F.when(F.col("side") == "BUY", F.lit(1)).otherwise(F.lit(-1)).cast(MONEY),
        )
        .withColumn("trade_date", F.to_date(F.col("transact_time")))
    )


def read_market(spark: SparkSession, run_date: str) -> DataFrame:
    schema = StructType([
        StructField("symbol", StringType(), True),
        StructField("asset_class", StringType(), True),
        StructField("close_price", StringType(), True),
        StructField("currency", StringType(), True),
        StructField("price_date", StringType(), True),
        StructField("_corrupt_record", StringType(), True),
    ])
    raw = (
        spark.read
        .option("header", "true")
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .schema(schema)
        .csv(f"s3a://{RAW}/market_data/dt={run_date}/")
    )
    close_text = blank_to_null(F.col("close_price"))
    close = close_text.cast(MONEY)
    reason = (
        F.when(F.col("_corrupt_record").isNotNull(), F.lit("malformed_line"))
        .when(close_text.isNull(), F.lit("missing_close_price"))
        .when(close.isNull() | (close <= 0), F.lit("non_positive_close_price"))
    )
    return (
        raw
        .withColumn("symbol", norm(F.col("symbol")))
        .withColumn("currency", norm(F.col("currency")))
        .withColumn("asset_class", F.lower(F.trim(F.col("asset_class"))))
        .withColumn("close_text", close_text)
        .withColumn("close_price", close)
        .withColumn("price_date", F.to_date(F.col("price_date")))
        .withColumn("reason", reason)
        .withColumn(
            "raw_record",
            F.coalesce(
                F.col("_corrupt_record"),
                F.concat_ws(
                    ",",
                    F.col("symbol"),
                    F.col("asset_class"),
                    F.coalesce(F.col("close_text"), F.lit("")),
                    F.col("currency"),
                ),
            ),
        )
    )


def portfolio_schema() -> StructType:
    position = StructType([
        StructField("symbol", StringType(), True),
        StructField("quantity", LongType(), True),
        StructField("currency", StringType(), True),
    ])
    limits = StructType([
        StructField("max_gross_exposure_usd", DoubleType(), True),
        StructField("max_position_pct", DoubleType(), True),
    ])
    return StructType([
        StructField("portfolio_id", StringType(), True),
        StructField("as_of", StringType(), True),
        StructField("positions", ArrayType(position), True),
        StructField("metadata", StructType([
            StructField("risk_limits", limits, True),
        ]), True),
    ])


def read_portfolios(spark: SparkSession, run_date: str) -> DataFrame:
    raw = (
        spark.read
        .option("multiLine", "true")
        .schema(portfolio_schema())
        .json(f"s3a://{RAW}/portfolio/dt={run_date}/")
    )
    exploded = raw.select(
        F.col("portfolio_id"),
        F.col("as_of"),
        F.explode(F.col("positions")).alias("position"),
        F.col("metadata.risk_limits.max_gross_exposure_usd").cast(MONEY).alias("max_gross_exposure_usd"),
        F.col("metadata.risk_limits.max_position_pct").cast(MONEY).alias("max_position_pct"),
    )
    return exploded.select(
        "portfolio_id",
        "as_of",
        norm(F.col("position.symbol")).alias("symbol"),
        F.col("position.quantity").cast(MONEY).alias("quantity"),
        norm(F.col("position.currency")).alias("currency"),
        "max_gross_exposure_usd",
        "max_position_pct",
        F.concat_ws(
            ",",
            F.col("portfolio_id"),
            F.col("position.symbol"),
            F.col("position.quantity").cast("string"),
            F.col("position.currency"),
        ).alias("raw_record"),
    )


def fx_rates(market: DataFrame) -> DataFrame:
    from_file = (
        market
        .filter(F.col("reason").isNull() & (F.col("asset_class") == "fx"))
        .select(F.col("symbol").alias("currency"), F.col("close_price").alias("fx_to_usd"))
    )
    usd = market.sparkSession.createDataFrame(
        [("USD", Decimal("1.000000"))],
        StructType([
            StructField("currency", StringType(), False),
            StructField("fx_to_usd", MONEY, False),
        ]),
    )
    return from_file.unionByName(usd).dropDuplicates(["currency"])


def write_parquet(df: DataFrame, path: str) -> None:
    df.coalesce(1).write.mode("overwrite").parquet(path)


def main(run_date: str) -> None:
    try:
        datetime.strptime(run_date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit("usage: etl_job.py YYYY-MM-DD")

    s3 = s3_client()
    for prefix in (
        f"trades/dt={run_date}/",
        f"market_data/dt={run_date}/",
        f"portfolio/dt={run_date}/",
    ):
        require_prefix(s3, prefix)

    spark = get_spark(f"fincore-etl-{run_date}")
    try:
        trades = read_trades(spark, run_date).cache()
        market = read_market(spark, run_date).cache()
        positions = read_portfolios(spark, run_date).cache()

        total = trades.count()
        if total == 0:
            raise SystemExit(f"NO INPUT trades for {run_date}")

        fx = fx_rates(market).cache()
        equities = (
            market
            .filter(F.col("reason").isNull() & (F.col("asset_class") == "equity"))
            .join(fx, "currency", "left")
        )
        equity_fx_missing = equities.filter(F.col("fx_to_usd").isNull())
        equities_ok = (
            equities
            .filter(F.col("fx_to_usd").isNotNull())
            .withColumn("close_price_usd", (F.col("close_price") * F.col("fx_to_usd")).cast(MONEY))
            .select(
                "symbol", "asset_class", "close_price", "currency", "price_date",
                "fx_to_usd", "close_price_usd",
            )
            .dropDuplicates(["symbol"])
        )
        fx_rows = (
            market
            .filter(F.col("reason").isNull() & (F.col("asset_class") == "fx"))
            .withColumn("fx_to_usd", F.col("close_price"))
            .withColumn("close_price_usd", F.col("close_price"))
            .select(
                "symbol", "asset_class", "close_price", "currency", "price_date",
                "fx_to_usd", "close_price_usd",
            )
        )
        clean_prices = equities_ok.unionByName(fx_rows)

        rule_rejects = trades.filter(F.col("reason").isNotNull())
        parsed = (
            trades
            .filter(F.col("reason").isNull())
            .join(fx, "currency", "left")
        )
        trade_fx_missing = parsed.filter(F.col("fx_to_usd").isNull())
        priced_candidates = (
            parsed
            .filter(F.col("fx_to_usd").isNotNull())
            .withColumn("price_usd", (F.col("price") * F.col("fx_to_usd")).cast(MONEY))
            .drop("fx_to_usd")
        )
        joined = priced_candidates.join(
            equities_ok.select("symbol", "close_price_usd"),
            "symbol",
            "left",
        ).cache()
        unpriced = joined.filter(F.col("close_price_usd").isNull())
        clean = (
            joined
            .filter(F.col("close_price_usd").isNotNull())
            .withColumn(
                "realized_pnl",
                (
                    (F.col("close_price_usd") - F.col("price_usd"))
                    * F.col("quantity")
                    * F.col("side_multiplier")
                ).cast(MONEY),
            )
            .select(
                "order_id", "portfolio_id", "symbol", "side", "quantity", "price",
                "currency", "transact_time", "trade_date", "close_price_usd",
                "price_usd", "realized_pnl",
            )
        )

        pos = positions.join(fx, "currency", "left").join(
            equities_ok.select("symbol", "close_price_usd"),
            "symbol",
            "left",
        )
        pos_reason = (
            F.when(F.col("quantity").isNull() | (F.col("quantity") <= 0), F.lit("bad_quantity"))
            .when(F.col("fx_to_usd").isNull(), F.lit("missing_fx_rate"))
            .when(F.col("close_price_usd").isNull(), F.lit("missing_close_price"))
        )
        pos = pos.withColumn("reason", pos_reason)
        pos_bad = pos.filter(F.col("reason").isNotNull())
        pos_ok = (
            pos
            .filter(F.col("reason").isNull())
            .withColumn(
                "market_value_usd",
                (F.col("quantity") * F.col("close_price_usd")).cast(MONEY),
            )
        )

        limits = positions.groupBy("portfolio_id").agg(
            F.first("max_gross_exposure_usd").alias("max_gross_exposure_usd"),
            F.first("max_position_pct").alias("max_position_pct"),
        )
        pnl_by_port = clean.groupBy("portfolio_id").agg(
            F.sum("realized_pnl").cast(MONEY).alias("total_pnl"),
        )
        value_by_port = pos_ok.groupBy("portfolio_id").agg(
            F.count(F.lit(1)).alias("position_count"),
            F.sum("market_value_usd").cast(MONEY).alias("total_market_value_usd"),
        )
        portfolio_pnl = (
            limits
            .join(pnl_by_port, "portfolio_id", "left")
            .join(value_by_port, "portfolio_id", "left")
            .select(
                "portfolio_id",
                F.to_date(F.lit(run_date)).alias("pnl_date"),
                F.coalesce(F.col("total_pnl"), F.lit(0).cast(MONEY)).alias("total_pnl"),
                F.coalesce(F.col("position_count"), F.lit(0)).alias("position_count"),
                F.coalesce(
                    F.col("total_market_value_usd"),
                    F.lit(0).cast(MONEY),
                ).alias("total_market_value_usd"),
                "max_gross_exposure_usd",
                "max_position_pct",
            )
        )

        market_bad = market.filter(F.col("reason").isNotNull())
        rejected = (
            reject_frame(rule_rejects, "trades", order_id="order_id", symbol="symbol", portfolio_id="portfolio_id")
            .unionByName(reject_frame(
                unpriced.withColumn("reason", F.lit("pnl_unresolvable")),
                "trades", order_id="order_id", symbol="symbol", portfolio_id="portfolio_id",
            ))
            .unionByName(reject_frame(
                trade_fx_missing.withColumn("reason", F.lit("missing_fx_rate")),
                "trades", order_id="order_id", symbol="symbol", portfolio_id="portfolio_id",
            ))
            .unionByName(reject_frame(market_bad, "market_data", symbol="symbol"))
            .unionByName(reject_frame(
                equity_fx_missing.withColumn("reason", F.lit("missing_fx_rate")),
                "market_data", symbol="symbol",
            ))
            .unionByName(reject_frame(
                pos_bad, "portfolio", symbol="symbol", portfolio_id="portfolio_id",
            ))
        )

        write_parquet(clean, f"s3a://{PROCESSED}/processed/trades/dt={run_date}/")
        write_parquet(portfolio_pnl, f"s3a://{PROCESSED}/processed/portfolio_pnl/dt={run_date}/")
        write_parquet(clean_prices, f"s3a://{PROCESSED}/processed/market_data/dt={run_date}/")
        write_parquet(rejected.select(*REJECT_FIELDS), f"s3a://{REJECTED}/rejected/dt={run_date}/")

        rule_rows = rule_rejects.groupBy("reason").count().collect()
        by_rule = {name: 0 for name in TRADE_RULES}
        for row in rule_rows:
            by_rule[row["reason"]] = int(row["count"])
        rule_total = sum(by_rule.values())
        clean_n = clean.count()
        unresolvable_n = unpriced.count()
        fx_missing_n = trade_fx_missing.count()
        if clean_n + rule_total + unresolvable_n + fx_missing_n != total:
            raise SystemExit(
                "trade buckets do not add up: "
                f"clean={clean_n} rules={rule_total} unresolvable={unresolvable_n} "
                f"missing_fx={fx_missing_n} total={total}"
            )

        pnl_sum = clean.agg(F.sum("realized_pnl")).collect()[0][0]
        reject_rate = (Decimal(rule_total) / Decimal(total)).quantize(Decimal("0.000001"))
        payload = {
            "trade_date": run_date,
            "total_trade_count": total,
            "clean_trade_count": clean_n,
            "rejection_count_by_rule": by_rule,
            "reject_rate": float(reject_rate),
            "pnl_unresolvable_count": unresolvable_n,
            "total_realized_pnl_usd": money_text(pnl_sum),
        }
        s3.put_object(
            Bucket=PROCESSED,
            Key=f"metrics/dt={run_date}/quality_metrics.json",
            Body=(json.dumps(payload, indent=2) + "\n").encode("utf-8"),
        )

        vod = (
            pos_ok
            .filter(F.col("symbol") == "VOD")
            .select("portfolio_id", "quantity", "close_price_usd", "market_value_usd")
            .limit(1)
            .collect()
        )
        print(
            f"[etl_job] date={run_date} total={total} clean={clean_n} "
            f"rejected={rule_total} unresolvable={unresolvable_n} "
            f"reject_rate={reject_rate} realized_pnl_usd={payload['total_realized_pnl_usd']}"
        )
        if vod:
            row = vod[0]
            print(
                "[etl_job] GBP check "
                f"portfolio={row['portfolio_id']} qty={row['quantity']} "
                f"close_usd={row['close_price_usd']} market_value_usd={row['market_value_usd']}"
            )
        print(f"[etl_job] wrote processed and rejected partitions for {run_date}")
    finally:
        spark.stop()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: etl_job.py YYYY-MM-DD")
    main(sys.argv[1])
