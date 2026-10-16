# 被動式 ETF 資料收集模組（Extract → MySQL）

負責專題的**資料收集（Extract）**：抓全台股標的 → 篩被動式 ETF → 從 Yahoo 抓股價/除權息/分割 → 寫進 MySQL，供後續選股/回測/報告使用。

## 資料流

```
FinMind(全台股清單) → 篩 ETF → 篩被動式(約 330 檔)
          │
          ▼
   Yahoo Finance API（依市場給 .TW / .TWO）抓 股價 / 除權息 / 分割
          │
          ▼
        MySQL（etf_price / etf_dividend / etf_split）
```

## 檔案

| 檔案 | 功能 |
|------|------|
| `etf_to_mysql.py` | 主流程：讀組員 athlan 的 `stock.etf_list` → 依市場抓價 → 寫進 MySQL 三張表 |
| `goal_calculator.py` | 讀 `etf_price` 算 ETF 含息報酬 + 六都房價 → 每月投入/能否付頭期款（結果寫回 `etf_cagr`/`goal_down_payment` 給 Redash） |
| `etf_universe.py` | 全台股→ETF→被動式（備援；清單主要讀 `stock.etf_list`） |
| `etf_worker.py` / `etf_tasks.py` / `etf_producer.py` | 分散式版：producer→RabbitMQ→Celery worker 抓價入庫 |
| `etf_scheduler.py` | apscheduler 定時更新（Airflow 的輕量替代） |
| `docker-compose-etf-swarm.yml` | Docker Swarm 部署檔 |
| `dags/etf_etl_dag.py` | Airflow DAG：每日定時更新 MySQL |
| `UNFINISHED.md` | **未完成/待辦事項**（帳號、連線、跨組員資料） |
| `schema.sql` | 建立三張資料表 |
| `Dockerfile` / `docker-compose.yml` | 打包 image、一鍵起 MySQL + 抓價入庫 |
| `pyproject.toml` / `uv.lock` | 依賴管理（uv：pandas、pymysql） |

## 資料表

- `etf_price(date, stock_id, adj_close)` — 每日**還原收盤**（算長期含息報酬用）
- `etf_dividend(stock_id, ex_date, amount)` — 除權息
- `etf_split(stock_id, split_date, numerator, denominator, ratio)` — 分割

> `stock_id` 存純代號（如 `0050`）；上市用 `.TW`、**上櫃用 `.TWO`**（很多債券 ETF 在上櫃）。

## 執行（本機，用 uv）

```bash
uv sync                                 # 裝好 pandas、pymysql
mysql etf < schema.sql                  # 先建表（或用 docker compose 自動建）
export MYSQL_HOST=localhost MYSQL_USER=你的帳號 MYSQL_PASSWORD=你的密碼 MYSQL_DB=etf
export ETF_LIMIT=15                      # （可選）先小量測試
uv run python etf_to_mysql.py            # 不設 ETF_LIMIT 就跑全部被動式 ETF
```

## Docker（course 12）

```bash
docker compose up --build                # 一鍵：起 MySQL（自動建表）+ 抓價入庫
```

> ⚠ **`Dockerfile` / `docker-compose.yml` / 下列指令中的 `mark0403` 是範例 Docker Hub 帳號，請改成你自己的帳號。**
```bash
docker build -t mark0403/etf-crawler:0.0.1 .   # ← mark0403 改成你的帳號
docker login
docker push mark0403/etf-crawler:0.0.1
```

## 資料來源

- 標的清單：**FinMind** `TaiwanStockInfo`。
- 股價/除權息/分割：**Yahoo Finance** chart API（`events=div,split`）。
- 「被動式」判定：依台股命名慣例近似判斷——排除槓桿(`L`)/反向(`R`)/主動(`A`)、名稱含正2/反1/主動；保留市值型、高股息、債券等追蹤指數的原型 ETF。
