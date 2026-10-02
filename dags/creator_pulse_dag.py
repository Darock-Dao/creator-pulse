import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

with DAG (
    dag_id="creator_pulse_pipeline",
    default_args = {
        "owner": "airflow",
        "depends_on_past": False,
        "email_on_failure": False,
        "retries": 2,                           # Max retries if a task fails
        "retry_delay": timedelta(minutes=5),    # Backoff time before retrying
    },
    description="Entire data pipeline for extracting YouTube data,"
                "copying to Snowflake,"
                "running DBT transformations and tests.",
    schedule_interval="0 */6 * * *",       # Cron expression (every 6 hours)
    start_date=datetime(2026, 1, 1),        # Fixed start date in the past
    catchup=False,                          # DO NOT run missed runs from start_date
    tags=["production", "creator_pulse"],
) as dag:

    fetch_youtube_task = PythonOperator(
        task_id="fetch_youtube_data",
        python_callable=None,  # The Python function to call
    )

    load_snowflake_task = PythonOperator(
        task_id="load_snowflake",
        python_callable=None,  
    )

    dbt_run_task = BashOperator(
        task_id="run_dbt",
        bash_command="cd /path/to/transform && ../.venv/bin/dbt run --profiles-dir .",
    )

    dbt_test_task = BashOperator(
        task_id="test_dbt",
        bash_command="cd /path/to/transform && ../.venv/bin/dbt run --profiles-dir .",
    )

    fetch_youtube_task >> load_snowflake_task >> dbt_run_task >> dbt_test_task

