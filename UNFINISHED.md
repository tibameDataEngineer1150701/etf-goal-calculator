# 未完成 / 待辦事項（ETF 資料收集模組）

> 這份記錄「程式已完成的部分」與「還缺什麼（程式 / 帳號 / 跨組員資料）」，方便接手與對接。

## ✅ 已完成（已實測）
- `etf_to_mysql.py`：讀組員 的 `stock.etf_list` → 依市場(.TW/.TWO) 抓 Yahoo 股價/除權息/分割 → 寫入 MySQL 三張表（讀不到清單會自動用 FinMind 備援）。
- `goal_calculator.py`：讀 `etf_price` 算各 ETF 含息年化報酬(CAGR) + 六都房價 → 每月需投入 / 每月投入 X 能否付頭期款；**結果寫回 `etf_cagr`、`goal_down_payment` 兩張表**（供 Redash）。
- `schema.sql`：五張表（etf_price / etf_dividend / etf_split / etf_cagr / goal_down_payment）。
- Docker 打包：`Dockerfile`、`docker-compose.yml`（含 MySQL，已實測 build + 入庫）。
- Docker Swarm：`docker-compose-etf-swarm.yml`（deploy/placement/overlay）。
- Airflow DAG：`dags/etf_etl_dag.py`（DockerOperator，每日收盤後更新）。
- 排程（簡易）：`etf_scheduler.py`（apscheduler）。
- 分散式（producer→RabbitMQ→worker）：`etf_worker.py` / `etf_tasks.py` / `etf_producer.py`（程式完成、import 與任務註冊已驗證）。

## ⬜ 未完成 / 待辦

### 需要「帳號 / 連線資訊」
- [ ] **Docker Hub**：image 尚未 push。Swarm / Airflow 都要從 Docker Hub pull。
      `docker build -t your-dockerhub-account/etf-crawler:0.0.1 . && docker login && docker push your-dockerhub-account/etf-crawler:0.0.1`
- [ ] **團隊共用 MySQL 連線**：`MYSQL_HOST`（Swarm 內為服務名 `mysql`）、`MYSQL_USER`、`MYSQL_PASSWORD`、埠號需統一。
- [ ] **團隊共用 RabbitMQ 連線**：`RABBITMQ_HOST`（Swarm 內為 `rabbitmq`）、帳密（預設 worker/worker）。
- [ ] **Airflow Variable**：DAG 內 `{{ var.value.mysql_password }}` 需在 Airflow 後台設定。

### 需要「跨組員資料」
- [ ] **組員 的 `stock.etf_list`**：需確認資料已寫進「團隊共用 MySQL」，本模組才讀得到（DB 名 `stock`、表 `etf_list`、欄位 `stock_id, market`）。
- [ ] **組員 的六都房價**：`goal_calculator.py` 的 `SIX_CITIES_PRICE_WAN` 目前是**佔位參數**，待實價登錄實際金額填入（或改成讀他的表）。

### 需要「環境 / 測試」
- [ ] **分散式端到端測試**：producer→RabbitMQ→worker 需在有 RabbitMQ 的環境實跑（開發沙箱無法啟動 RabbitMQ）。
      啟動工人：`uv run celery -A etf_tasks worker --loglevel=info`；發送任務：`uv run python etf_producer.py`
- [ ] **Airflow 本體**：目前只有 DAG 檔，需放進 Airflow 環境（課程 `dataflow` repo 或自架）才會真的定時跑。
- [ ] **Docker Swarm 多機**：需在 Swarm 叢集（多 Node）實際部署、設 Node Labels。

### 文件
- [ ] **架構圖（draw.io）** 更新並上傳團隊 repo。
- [ ] （選擇性）`goal_calculator` 讓房價隨時間用 Real HPI 推估未來值。

## 相關檔案
`etf_to_mysql.py`、`goal_calculator.py`、`etf_universe.py`(備援)、`etf_worker.py`/`etf_tasks.py`/`etf_producer.py`、`etf_scheduler.py`、`schema.sql`、`Dockerfile`、`docker-compose.yml`、`docker-compose-etf-swarm.yml`、`dags/etf_etl_dag.py`、`README_etf.md`
