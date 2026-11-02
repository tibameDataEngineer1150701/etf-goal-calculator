# Airflow DAG：交易日 15:00 更新 ETF 還原收盤。
# VM 的 overlay etf_etf 不允許 docker run 直接加入，所以建立 Swarm service。
# image 從 Docker Hub 拉：mark0403/etf-crawler:0.0.1。
# 若 swarm.yml 的 scheduler 已經在跑，不要再啟用這支 DAG，避免同一時間抓兩次。

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.docker.operators.docker_swarm import DockerSwarmOperator

default_args = {
    "owner": "mark0403",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="etf_price_etl",
    default_args=default_args,
    description="每天收盤後抓被動式 ETF 還原收盤，自動更新 MySQL",
    schedule_interval="0 15 * * 1-5",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    tags=["etf", "etl", "專題"],
) as dag:

    run_etf_crawler = DockerSwarmOperator(
        task_id="run_etf_crawler",
        image="mark0403/etf-crawler:0.0.1",
        api_version="auto",
        auto_remove="success",
        force_pull=True,
        command="uv run python etf_to_mysql.py",
        tty=True,
        enable_logging=True,
        environment={
            "MYSQL_HOST": "mysql",
            "MYSQL_PORT": "3306",
            "MYSQL_USER": "root",
            "MYSQL_PASSWORD": "rootpass",
            "MYSQL_DB": "etf",
            "ETF_LIST_DB": "stock",
            "ETF_LIST_TABLE": "etf_list",
        },
        networks=["etf_etf"],
        placement=["node.role == manager"],
        docker_url="unix://var/run/docker.sock",
        mount_tmp_dir=False,
    )

    run_etf_crawler
