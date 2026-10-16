# ETF 分散式爬蟲 — Celery worker（連 RabbitMQ）
# 對應課程 14（RabbitMQ + Celery）、21（.env 環境變數）
# 啟動工人：  uv run celery -A etf_tasks worker --loglevel=info
#   （-A 指向 etf_tasks，裡面會 import 本檔的 app 並註冊任務）

import os
from celery import Celery

# RabbitMQ 連線資訊從環境變數讀（DOCKER 環境用服務名稱 rabbitmq）
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "127.0.0.1")
RABBITMQ_PORT = os.environ.get("RABBITMQ_PORT", "5672")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "worker")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "worker")

# broker 用變數，不寫死 127.0.0.1（course 21）
BROKER_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}//"

app = Celery("etf", broker=BROKER_URL)
