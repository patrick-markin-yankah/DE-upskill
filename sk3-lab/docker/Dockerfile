FROM apache/airflow:2.9.3-python3.11

# Java is required by PySpark (Spark runs on the JVM)
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# Debian names the JDK dir after the CPU arch (amd64 vs arm64 on Apple Silicon)
ARG TARGETARCH
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-${TARGETARCH}

# Python packages must be installed as the airflow user, never as root
USER airflow

# Airflow's 2.9.3 constraint file pins a known-good set (amazon 8.25.0, boto3 1.34.131,
# pyspark 3.5.1). Installing those together without it made pip backtrack until it crashed.
ARG CONSTRAINT_URL=https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.11.txt
RUN pip install --no-cache-dir \
    "apache-airflow==2.9.3" \
    "apache-airflow-providers-amazon==8.25.0" \
    boto3==1.34.131 \
    pyspark==3.5.1 \
    --constraint "${CONSTRAINT_URL}"

# dbt-postgres 1.8.2 allows any dbt-adapters <2. Pip then walks 1.22+ (dbt-protos),
# which fights Airflow's protobuf and raises ResolutionTooDeep. Pin the 1.8-era stack.
RUN pip install --no-cache-dir \
    "apache-airflow==2.9.3" \
    dbt-postgres==1.8.2 \
    dbt-core==1.8.2 \
    dbt-adapters==1.2.1 \
    dbt-common==1.3.0
