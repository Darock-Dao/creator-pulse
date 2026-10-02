import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Add project root to sys.path so Airflow can find the 'src' directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from src import fetch_youtube, load_snowflake

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

TRANSFORM_DIR = os.path.join(PROJECT_ROOT, "transform")
DBT_BIN = os.path.join(PROJECT_ROOT, ".venv", "bin", "dbt")

bash_run_command=f"cd {TRANSFORM_DIR} && {DBT_BIN} run --profiles-dir ."
bash_test_command=f"cd {TRANSFORM_DIR} && {DBT_BIN} test --profiles-dir ."

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
        bash_command=bash_run_command,
    )

    dbt_test_task = BashOperator(
        task_id="test_dbt",
        bash_command=bash_test_command
    )

    fetch_youtube_task >> load_snowflake_task >> dbt_run_task >> dbt_test_task
