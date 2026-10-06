#!/bin/bash
# One-time Airflow bootstrap: metadata tables, admin user, MinIO and Slack connections.
set -euo pipefail

airflow db migrate

airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com \
  || echo "admin user already exists"

python /opt/airflow/init_connections.py
