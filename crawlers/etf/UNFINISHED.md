# 第 5 次專題目標

## 1. Airflow 改成自己的，且 build Docker image

- [x] `dags/etf_etl_dag.py`、`docker/Dockerfile` 已有。本機 `docker compose` 可建出 image。
- [ ] image 名稱仍是 `your-dockerhub-account/etf-crawler:0.0.1`，尚未改成自己的 Docker Hub 帳號，也尚未 `docker push`。
- [ ] DAG 的 owner、image 要改成自己的；Airflow Variable `mysql_password` 尚未設定。

## 2. Airflow 結合 producer、Celery，定時發送任務

- [x] `etf_producer.py`、`etf_tasks.py`、`etf_worker.py` 已有。排程時間訂為週一到週五 15:00。
- [ ] DAG 現在是直接跑 `etf_to_mysql.py`，沒有呼叫 producer，也沒有把任務送進 Celery。
- [ ] producer → RabbitMQ → worker 尚未在有 RabbitMQ 的環境跑過。
- [ ] 這條流程尚未在 Airflow 裡定時觸發成功。

## 3. Redash 畫圖，或用 Line 發通知給自己

- [x] 試算結果已寫入 `etf_cagr`、`goal_down_payment`。
- [x] Redash 可調單一 ETF、頭期款比例、年數、每月投入。見 README。
- [ ] 尚未接 Line 通知。

## 4. code、yml 上傳 GitHub

- [x] 程式、`docker/docker-compose.yml`、`swarm.yml`、DAG 已在 `main`。

## 5. 架構圖更新、README 更新

- [x] `README.md` 已寫團隊目錄、Docker、試算與 Redash 操作。
- [ ] README 尚未寫 Airflow、Celery 或 Line 的用法。
- [ ] 架構圖尚未更新並上傳。

## 仍待團隊資料

- [ ] 團隊 MySQL、RabbitMQ 的主機與帳密。
- [ ] `stock.etf_list`（`stock_id`、`market`）。讀不到時目前改走 FinMind。
- [x] 六都房價。`housing.city_house_price` 為 2026Q3 住宅成交總價中位數；讀不到時試算才用手填粗估。
