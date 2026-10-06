"""Create FinCore's MinIO buckets. Safe to re-run."""
import os

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["MINIO_ENDPOINT"],
    aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
)

BUCKETS = ["fincore-raw", "fincore-processed", "fincore-rejected"]

for bucket in BUCKETS:
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"exists : {bucket}")
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"created: {bucket}")
