# 未完成 / 待辦事項（ETF 資料收集模組）

## 已完成（已實測）

- `etf_to_mysql.py`：讀 `stock.etf_list` → 依市場（`.TW` / `.TWO`）抓 Yahoo 股價 / 除權息 / 分割 → 寫入 MySQL。讀不到清單會改用 FinMind。
- `goal_calculator.py`：讀 `etf_price` 算各 ETF 含息年化報酬，搭配六都房價試算每月需投入與能否付頭期款。結果寫回 `etf_cagr`、`goal_down_payment`。
- `schema.sql`：五張表（`etf_price` / `etf_dividend` / `etf_split` / `etf_cagr` / `goal_down_payment`）。
- Docker：`docker/Dockerfile`、`docker/docker-compose.yml`。
- Swarm：`swarm.yml`。
- Airflow DAG：`dags/etf_etl_dag.py`。
- 排程：`etf_scheduler.py`。
- 分散式：`etf_worker.py` / `etf_tasks.py` / `etf_producer.py`。

## 待辦

### 帳號 / 連線

- [ ] **Docker Hub**：image 尚未 push。Swarm 與 Airflow 都要從 Docker Hub pull。
      `docker build -f docker/Dockerfile -t your-dockerhub-account/etf-crawler:0.0.1 .`
- [ ] **團隊共用 MySQL**：`MYSQL_HOST`（Swarm 內為服務名 `mysql`）、`MYSQL_USER`、`MYSQL_PASSWORD`、埠號需統一。
- [ ] **團隊共用 RabbitMQ**：`RABBITMQ_HOST`（Swarm 內為 `rabbitmq`）、帳密（預設 worker / worker）。
- [ ] **Airflow Variable**：DAG 內 `{{ var.value.mysql_password }}` 需在 Airflow 後台設定。

### 跨組員資料

- [ ] **`stock.etf_list`**：需確認已寫進團隊共用 MySQL（DB 名 `stock`、表 `etf_list`、欄位 `stock_id, market`）。
- [ ] **六都房價**：`goal_calculator.py` 的 `SIX_CITIES_PRICE_WAN` 仍是佔位參數，待實價登錄金額填入，或改成讀房市資料表。

### 環境

- [ ] **分散式端到端**：producer → RabbitMQ → worker 需在有 RabbitMQ 的環境實跑。
      啟動工人：`uv run celery -A etf_tasks worker --loglevel=info`；發送任務：`uv run python etf_producer.py`
- [ ] **Airflow**：目前只有 DAG 檔，放進 Airflow 的 `dags/` 後才會定時跑。
- [ ] **Docker Swarm**：需在 Swarm 叢集實際部署，並設定 Node Label `etf_crawler`。

### 文件

- [ ] 架構圖更新並上傳團隊 repo。
- [ ] （選擇性）`goal_calculator` 讓房價隨時間用房價指數推估未來值。
