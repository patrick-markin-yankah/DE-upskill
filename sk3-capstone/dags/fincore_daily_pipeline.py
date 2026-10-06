"""FinCore overnight pipeline.

Sensors → extract → Spark → quality gate → load → dbt → ops row.
A failed gate records published=false and does not load.
A failed dbt test alerts and still exits 0. The load stays.
"""
import sys
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.utils.session import create_session
from airflow.utils.state import TaskInstanceState
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

sys.path.insert(0, "/opt/airflow/jobs")

import alerts
import record_run

DAG_ID = "fincore_daily_pipeline"
RAW_BUCKET = "fincore-raw"
SENSORS = {
    "wait_for_trades": ("trades", "trades/dt={{ ds }}/*"),
    "wait_for_market_data": ("market_data", "market_data/dt={{ ds }}/*"),
    "wait_for_portfolio": ("portfolio", "portfolio/dt={{ ds }}/*"),
}
OPEN_SENSOR_STATES = {
    TaskInstanceState.SCHEDULED,
    TaskInstanceState.QUEUED,
    TaskInstanceState.RUNNING,
    TaskInstanceState.UP_FOR_RESCHEDULE,
    TaskInstanceState.UP_FOR_RETRY,
    TaskInstanceState.DEFERRED,
    None,
}


def _fail_sibling_sensors(context) -> None:
    this_id = context["task_instance"].task_id
    dag_run = context["dag_run"]
    with create_session() as session:
        for task_id in SENSORS:
            if task_id == this_id:
                continue
            sibling = dag_run.get_task_instance(task_id, session=session)
            if sibling is not None and sibling.state in OPEN_SENSOR_STATES:
                sibling.set_state(TaskInstanceState.FAILED, session=session)
                print(f"[sensor] marked {task_id} failed so it stops poking")


def _on_failure(context) -> None:
    ti = context["task_instance"]
    try:
        if ti.task_id in SENSORS:
            source = SENSORS[ti.task_id][0]
            alerts.deliver(
                f"Missing source: {source} for {context['ds']}. Run aborted.",
                alerts.OUT_DIR / f"{context['ds']}_{ti.task_id}.json",
                {
                    "event": "missing_source",
                    "ds": context["ds"],
                    "task": ti.task_id,
                    "source": source,
                    "try_number": ti.try_number,
                    "log_url": ti.log_url,
                },
            )
            _fail_sibling_sensors(context)
            return
        alerts.deliver(
            (
                "FinCore task failed. "
                f"task={ti.task_id} date={context['ds']} attempt={ti.try_number} log={ti.log_url}"
            ),
            alerts.OUT_DIR / f"{context['ds']}_{ti.task_id}.json",
            {
                "event": "task_failed",
                "ds": context["ds"],
                "task": ti.task_id,
                "try_number": ti.try_number,
                "log_url": ti.log_url,
            },
        )
    except Exception as exc:
        print(f"[on_failure] alert copy failed: {exc}")


def _on_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis) -> None:
    try:
        seen = set()
        log_url = ""
        if blocking_tis:
            log_url = getattr(blocking_tis[0], "log_url", "") or ""
        for sla in slas:
            when = getattr(sla, "execution_date", None)
            ds = when.strftime("%Y-%m-%d") if when else "unknown"
            if ds in seen:
                continue
            seen.add(ds)
            alerts.deliver(
                f"PAGE. Pipeline missed the 6-hour SLA. date={ds} log={log_url}",
                alerts.OUT_DIR / f"page_{ds}.json",
                {"event": "sla_page", "ds": ds, "log_url": log_url},
            )
    except Exception as exc:
        print(f"[sla] page copy failed: {exc}")


def _choose_branch(**context) -> str:
    metrics = record_run.read_metrics(context["ds"])
    if metrics and record_run.gate_passes(metrics):
        print(
            f"[quality_gate] pass date={context['ds']} "
            f"reject_rate={metrics['reject_rate']} "
            f"unresolvable={metrics['pnl_unresolvable_count']}"
        )
        return "load.begin"
    print(f"[quality_gate] fail date={context['ds']} metrics={metrics}")
    return "alert_quality_gate"


def _alert_quality_gate(**context) -> None:
    metrics = record_run.read_metrics(context["ds"]) or {}
    record_run.record_from_context(context, published=False, dbt_tests_passed=False)
    rate = metrics.get("reject_rate", "")
    unresolvable = metrics.get("pnl_unresolvable_count", "")
    alerts.deliver(
        (
            "Quality gate failed. "
            f"date={context['ds']} reject_rate={rate} limit=0.02 "
            f"unresolvable={unresolvable} limit=100. Load skipped."
        ),
        alerts.OUT_DIR / f"{context['ds']}_quality_gate.json",
        {
            "event": "quality_gate",
            "ds": context["ds"],
            "task": "alert_quality_gate",
            "reject_rate": rate,
            "unresolvable": unresolvable,
        },
    )
    raise AirflowFailException("quality gate failed; load skipped")


def _record_published(**context) -> None:
    raw = context["ti"].xcom_pull(task_ids="dbt.dbt_test")
    passed = str(raw or "").strip().lower() == "passed"
    record_run.record_from_context(context, published=True, dbt_tests_passed=passed)


default_args = {
    "owner": "data-eng",
    "retries": 0,
    "on_failure_callback": _on_failure,
}

with DAG(
    dag_id=DAG_ID,
    description="Weekday FinCore load. 00:30 UTC, SLA 6 hours.",
    start_date=pendulum.datetime(2026, 9, 21, tz="UTC"),
    schedule="30 0 * * 1-5",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    sla_miss_callback=_on_sla_miss,
    tags=["fincore", "sk03"],
) as dag:
    sensors = []
    for task_id, (source, key) in SENSORS.items():
        sensor = S3KeySensor(
            task_id=task_id,
            aws_conn_id="minio_s3",
            bucket_name=RAW_BUCKET,
            bucket_key=key,
            wildcard_match=True,
            mode="reschedule",
            poke_interval=600,
            timeout=14400,
            retries=0,
        )
        extract = BashOperator(
            task_id=f"extract_{source}",
            bash_command=f"python /opt/airflow/jobs/extract_source.py {source} {{{{ ds }}}}",
        )
        sensor >> extract
        sensors.append(extract)

    sources_ready = EmptyOperator(task_id="sources_ready")
    sensors >> sources_ready

    spark_etl = BashOperator(
        task_id="spark_etl",
        bash_command="python /opt/airflow/jobs/etl_job.py {{ ds }}",
        retries=3,
        retry_delay=timedelta(minutes=15),
        execution_timeout=timedelta(hours=2),
    )

    quality_gate = BranchPythonOperator(
        task_id="quality_gate",
        python_callable=_choose_branch,
    )

    alert_quality_gate = PythonOperator(
        task_id="alert_quality_gate",
        python_callable=_alert_quality_gate,
    )

    with TaskGroup(group_id="load") as load_group:
        load_begin = EmptyOperator(task_id="begin")
        load_warehouse = BashOperator(
            task_id="load_warehouse",
            bash_command="python /opt/airflow/jobs/load_warehouse.py {{ ds }}",
        )
        load_begin >> load_warehouse

    with TaskGroup(group_id="dbt") as dbt_group:
        dbt_run = BashOperator(
            task_id="dbt_run",
            cwd="/opt/airflow/dbt/fincore_analytics",
            bash_command="dbt run --profiles-dir /opt/airflow/dbt",
        )
        dbt_test = BashOperator(
            task_id="dbt_test",
            cwd="/opt/airflow/dbt/fincore_analytics",
            bash_command=(
                "if dbt test --profiles-dir /opt/airflow/dbt; then "
                "echo passed; "
                "else "
                "python /opt/airflow/jobs/alerts.py --event dbt_advisory "
                "--ds {{ ds }} --task dbt_test --log-url \"{{ ti.log_url }}\"; "
                "echo failed; "
                "fi"
            ),
        )
        dbt_run >> dbt_test

    record = PythonOperator(
        task_id="record_run",
        python_callable=_record_published,
        sla=timedelta(hours=6),
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    sources_ready >> spark_etl >> quality_gate
    quality_gate >> [alert_quality_gate, load_group]
    load_group >> dbt_group >> record
