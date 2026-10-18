from urllib.parse import quote

from celery import Celery

from crawler.config import (
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    WORKER_ACCOUNT,
    WORKER_PASSWORD,
)

# 將帳密中的特殊字元轉成網址可用的格式
account = quote(WORKER_ACCOUNT, safe="")
password = quote(WORKER_PASSWORD, safe="")

app = Celery(
    "etf_practice",
    broker=f"pyamqp://{account}:{password}@{RABBITMQ_HOST}:{RABBITMQ_PORT}//",
    include=["crawler.tasks"],
)

# 使用自己的佇列，避免與老師的 celery 示範佇列混在一起
app.conf.update(
    task_default_queue="etf_list",
    task_serializer="json",
    accept_content=["json"],
    timezone="Asia/Taipei",
)