"""List one raw prefix and write a manifest. Does not parse the file.

Usage: python extract_source.py trades|market_data|portfolio YYYY-MM-DD
"""
import json
import os
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

BUCKET = "fincore-raw"
SOURCES = {
    "trades": "trades",
    "market_data": "market_data",
    "portfolio": "portfolio",
}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


def list_objects(s3, prefix: str) -> list[dict]:
    objects = []
    token = None
    try:
        while True:
            kwargs = {"Bucket": BUCKET, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                if obj["Key"].endswith("/"):
                    continue
                objects.append({"key": obj["Key"], "size": obj["Size"]})
            if not resp.get("IsTruncated"):
                break
            token = resp["NextContinuationToken"]
    except ClientError as exc:
        raise SystemExit(f"could not list s3://{BUCKET}/{prefix}: {exc}") from exc
    return objects


def main(source: str, run_date: str) -> None:
    if source not in SOURCES:
        raise SystemExit(f"source must be one of: {', '.join(SOURCES)}")
    try:
        datetime.strptime(run_date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit("usage: extract_source.py trades|market_data|portfolio YYYY-MM-DD")

    prefix = f"{SOURCES[source]}/dt={run_date}/"
    s3 = s3_client()
    objects = list_objects(s3, prefix)
    if not objects:
        raise SystemExit(f"NO INPUT at s3://{BUCKET}/{prefix}")

    payload = {
        "source": source,
        "trade_date": run_date,
        "object_count": len(objects),
        "objects": objects,
    }
    key = f"_manifests/dt={run_date}/{source}.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=(json.dumps(payload, indent=2) + "\n").encode("utf-8"),
    )
    print(f"[extract_source] s3://{BUCKET}/{key} objects={len(objects)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_source.py trades|market_data|portfolio YYYY-MM-DD")
    main(sys.argv[1], sys.argv[2])
