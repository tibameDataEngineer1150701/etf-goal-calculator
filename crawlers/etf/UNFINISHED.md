# 依課程講義尚未完成的清單

順序跟 `crawlers/finmind/docs/course-notes.md` 的學習順序、啟動順序相同。已完成的打勾，剩下的由上往下做。

## 已經在跑

- [x] Python 3.11、uv、環境變數連線。
- [x] MySQL 與 phpMyAdmin（`docker/docker-compose.yml`，埠 3306、8080）。
- [x] 爬蟲直接寫進 MySQL（`etf_to_mysql.py`）。這一步在講義裡是 Celery 任務，目前還是一支程式直接寫。
- [x] 基本 Dockerfile，本機可以 build。
- [x] 頭期款試算、Redash、程式與 yml 已在 GitHub。

## 1. 環境設定

- [x] `genenv.py` 依 DEV 以外的 `DOCKER`、`PRODUCTION` 讀 `local.ini` 產生 `.env`。範本是 `local.ini.example`，密碼不要提交。

## 2. Worker 與 Task

- [x] `etf_worker.py`、`etf_tasks.py` 已有。
- [x] RabbitMQ 與 Flower 已可啟動。Flower 在 http://localhost:5555 ，RabbitMQ 管理畫面在 http://localhost:15672 。
- [x] Worker 連上 RabbitMQ。上市 worker 收到 0050 後寫入 2917 筆股價。

## 3. Producer

- [x] `etf_producer.py` 依市場把任務送到 `twse` 或 `tpex`。
- [x] 已實際派送，worker 寫進 MySQL。

## 4. 爬蟲任務本體

- [x] `etf.crawl_one` 重用 `etf_to_mysql.py` 的抓價與寫入。0050、006201 都回報 succeeded。

## 5. 多 queue

- [x] 上市 `twse`、上櫃 `tpex` 各一個 worker。006201 由上櫃 worker 寫入。

## 6. Scheduler

- [x] `etf_scheduler.py` 改為呼叫 producer。時間仍是週一到週五 15:00。
- [ ] 排程容器尚未在 15:00 自動觸發過。可用 `--profile schedule` 啟動後再觀察。

## 7. Compose：worker、producer、scheduler

- [x] `docker/celery-compose.yml` 含 RabbitMQ、Flower、兩個 worker、producer、scheduler。
- [x] 啟動順序：先起 MySQL，再起這個 compose，然後用 `--profile dispatch` 派送。

## 8. Docker image

- [x] 基本版之外，已有 `docker/with.env.Dockerfile`、`docker/prod.with.env.Dockerfile`。build 時用 `local.ini.example` 產生 `.env`，正式密碼要自己改。
- [x] image 名稱是 `mark0403/etf-crawler:0.0.1`。
- [x] `docker push`。DAG 與 `swarm.yml` 的 image、owner 都是 `mark0403`。

## 9. Swarm

- [x] `swarm.yml` 已有（ETF 爬蟲，等 image 推上 Docker Hub 再部署）。
- [x] `docker/portainer.yml` 已有。GCP 這一階段只部署 Swarm 與 Portainer。
- [ ] 在 GCP VM 執行 `docker swarm init`，再開防火牆 9000，然後 `docker stack deploy -c docker/portainer.yml portainer`。
- [ ] 建立 overlay 網路，用已 push 的 image 部署爬蟲。節點需要 `etf_crawler` 標籤。這一步排在 Portainer 之後。

## 10. Airflow

- [x] `dags/etf_etl_dag.py` 已有，週一到週五 15:00。
- [x] DAG 改成 KubernetesPodOperator，只跑 `etf_producer.py`，任務送到 VM 的 RabbitMQ。
- [ ] 在 Composer 設定 Airflow Variable `mysql_password`、`rabbitmq_password`。
- [ ] 在 Airflow 裡定時觸發成功一次。
- [ ] README 補上 Airflow、Celery 的操作說明。

## 11. 講義最後一節：GCP

這段在 FinMind 範例裡，ETF 試算目前沒有用到。

- [ ] `gcloud` 登入並設定專案。
- [ ] 股價上傳 BigQuery。
- [ ] Secret Manager 讀取密鑰。

## 文件

- [ ] 架構圖尚未更新並上傳。
