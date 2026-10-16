# Airflow DAG：每天定時更新專題 ETF 資料（讓 MySQL 自動定期更新）
# 對應課程 28（Airflow / DockerOperator）；滿足作業「建立 DAG + 專題 MySQL 資料自動定期更新」
#
# 放置位置：Airflow 的 dags/ 資料夾（例如課程 dataflow repo 的 dags/）
# 說明：用 DockerOperator 跑「你自己 build 並 push 到 Docker Hub 的 ETF image」，
#       image 的預設 CMD 就是 etf_to_mysql.py（讀 stock.etf_list → 抓價 → 寫 etf_price）。

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

default_args = {
    "owner": "mark0403",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="etf_price_etl",
    default_args=default_args,
    description="每天收盤後抓被動式 ETF 股價/除權息/分割，自動更新 MySQL",
    schedule_interval="0 15 * * 1-5",      # 週一~週五 15:00（台股收盤後）；cron 格式
    start_date=datetime(2026, 10, 1),
    catchup=False,
    tags=["etf", "etl", "專題"],
) as dag:

    run_etf_crawler = DockerOperator(
        task_id="run_etf_crawler",
        # ⚠ mark0403 請改成你自己的 Docker Hub image
        image="mark0403/etf-crawler:0.0.1",
        auto_remove=True,
        # 用 image 的預設 CMD（etf_to_mysql.py）；command 留空即可
        environment={
            "MYSQL_HOST": "mysql",
            "MYSQL_PORT": "3306",
            "MYSQL_USER": "root",
            "MYSQL_PASSWORD": "{{ var.value.mysql_password }}",  # 在 Airflow Variables 設定
            "MYSQL_DB": "etf",
            "ETF_LIST_DB": "stock",         # 讀組員 athlan 的 stock.etf_list
            "ETF_LIST_TABLE": "etf_list",
        },
        network_mode="my_swarm_network",    # 跟 mysql 同一 overlay 內網
        docker_url="unix://var/run/docker.sock",
        mount_tmp_dir=False,
    )

    # 單一任務的 DAG；若未來要串接「抓價 → 算報酬 → 視覺化」，可用 >> 串起來：
    #   run_etf_crawler >> run_goal_calculator >> ...
    run_etf_crawler
