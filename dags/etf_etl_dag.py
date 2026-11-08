# Composer（GKE）上的股價排程。
# 到點只跑 producer，把 stock.etf_list 送到 VM 上的 RabbitMQ。
# 抓價仍由 VM 的上市、上櫃 worker 完成。
# Composer 不能用 DockerSwarmOperator，這裡用 KubernetesPodOperator。
#
# 啟用前要先把 etf-jobs 的 scheduler 停掉，避免同一時間送兩次。
# 連線密碼放 Composer 的 Airflow Variables：mysql_password、rabbitmq_password。
# 主機是 etf-goal 裡這台 VM 的內部 IP，Composer 要建在同一個專案、同一個 VPC。

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

default_args = {
    "owner": "mark0403",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="etf_price_etl",
    default_args=default_args,
    description="收盤後把 ETF 清單送到自己的 RabbitMQ，由 VM worker 抓價",
    schedule="0 15 * * 1-5",
    start_date=datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Taipei")),
    catchup=False,
    is_paused_upon_creation=True,
    tags=["etf", "etl", "專題"],
) as dag:

    send_etf_tasks = KubernetesPodOperator(
        task_id="send_etf_tasks",
        name="etf-producer",
        namespace="composer-user-workloads",
        image="mark0403/etf-crawler:0.0.2.composer",
        image_pull_policy="Always",
        cmds=["uv", "run", "python", "etf_producer.py"],
        config_file="/home/airflow/composer_kube_config",
        get_logs=True,
        on_finish_action="delete_pod",
        env_vars={
            "MYSQL_HOST": "10.140.0.2",
            "MYSQL_PORT": "3306",
            "MYSQL_USER": "root",
            "MYSQL_PASSWORD": "{{ var.value.mysql_password }}",
            "MYSQL_DB": "etf",
            "ETF_LIST_DB": "stock",
            "ETF_LIST_TABLE": "etf_list",
            "RABBITMQ_HOST": "10.140.0.2",
            "RABBITMQ_PORT": "5672",
            "RABBITMQ_USER": "worker",
            "RABBITMQ_PASSWORD": "{{ var.value.rabbitmq_password }}",
        },
    )

    send_etf_tasks
