# 共同專案

```
crawlers/          各組員的 Python 程式
  etf/             ETF 爬蟲與目標試算
  stock/           其他台股資料
  housing/         房市資料
  cpi/             總體經濟資料
dags/              各自的 Airflow DAG
docker/            共用 Docker 設定
swarm.yml          共用 Swarm 部署設定
```

## ETF 資料流

FinMind 全台股清單 → 篩被動式 ETF → Yahoo Finance 抓股價 / 除權息 / 分割 → MySQL。

| 路徑 | 功能 |
|------|------|
| `crawlers/etf/etf_to_mysql.py` | 讀 `stock.etf_list`，依市場抓價，寫進 MySQL |
| `crawlers/etf/goal_calculator.py` | 用 `etf_price` 算含息報酬，搭配六都房價試算頭期款 |
| `crawlers/etf/etf_universe.py` | 讀不到資料庫清單時，改從 FinMind 篩被動式 ETF |
| `crawlers/etf/etf_producer.py` / `etf_tasks.py` / `etf_worker.py` | producer → RabbitMQ → Celery worker |
| `crawlers/etf/etf_scheduler.py` | 還沒接上 Airflow 時的定時更新 |
| `crawlers/etf/schema.sql` | 建表 |
| `dags/etf_etl_dag.py` | 每個交易日收盤後更新 |
| `docker/Dockerfile` / `docker/docker-compose.yml` | 打包 image、一鍵起 MySQL 與抓價 |
| `swarm.yml` | Swarm 部署 |

資料表：`etf_price`、`etf_dividend`、`etf_split`、`etf_cagr`、`goal_down_payment`。`stock_id` 存純代號（如 `0050`）；上市用 `.TW`，上櫃用 `.TWO`。

## 本機執行

在 `crawlers/etf/`：

```bash
uv sync
mysql etf < schema.sql
export MYSQL_HOST=localhost MYSQL_USER=你的帳號 MYSQL_PASSWORD=你的密碼 MYSQL_DB=etf
export ETF_LIMIT=15
uv run python etf_to_mysql.py
```

## Docker

在專案根目錄：

```bash
docker compose -f docker/docker-compose.yml up --build
```

推上 Docker Hub 時，把 `your-dockerhub-account` 改成自己的帳號：

```bash
docker build -f docker/Dockerfile -t your-dockerhub-account/etf-crawler:0.0.1 .
docker login
docker push your-dockerhub-account/etf-crawler:0.0.1
```

## 資料來源

- 標的清單：FinMind `TaiwanStockInfo`。讀不到時才用；平常讀 `stock.etf_list`。
- 股價 / 除權息 / 分割：Yahoo Finance chart API（`events=div,split`）。
- 被動式判定：排除槓桿（`L`）、反向（`R`）、主動（`A`），以及名稱含正2 / 反1 / 主動的商品。
