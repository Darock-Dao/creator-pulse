import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

with DAG (
    dag_id="my_pipeline_name",
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
    pass