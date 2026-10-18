# ETF 目標試算

用被動式 ETF 的歷史報酬，試算六都頭期款要每月存多少。股價、房價與試算結果都放在 MySQL，圖表用 Redash。

> **專案狀態：開發中。** 清單、股價入庫、頭期款試算與 Redash 已在本機 MySQL 跑過。Airflow 目前直接執行抓價程式，尚未改成 Producer → RabbitMQ → Celery。Docker Hub 帳號尚未完成。

## 專案目的與資料範圍

- **ETF 清單**：`stock.etf_list`。欄位用 `stock_id`、`market`（`twse` 或 `tpex`）。程式在 `crawlers/stock`。
- **股價**：Yahoo Finance chart。上市 `.TW`、上櫃 `.TWO`。寫入還原收盤 `adj_close`、除權息與分割。
- **六都房價**：`housing.city_house_price.median_total_wan`，單位是萬元，內容為住宅成交總價中位數。房市、房價指數與 CPI 的爬蟲在 `crawlers/housing`。
- **試算輸出**：`etf.etf_cagr`、`etf.goal_down_payment`。
- **後續應用**：單一 ETF、頭期款比例、年數與每月投入可在 Redash 調整。

`crawlers/finmind` 是另一套 FinMind 日線爬蟲，寫入自己的行情表。本專案的報酬計算主要讀取的是etf.etf_price`。

## 系統架構

```text
[Airflow / etf_scheduler：已有程式，待接上 Celery]
            |
            v
        Producer
            |
            v
         RabbitMQ
            |
            v
       Celery Worker
            |
            v
 stock.etf_list → Yahoo Finance chart
            |
            v
      pandas DataFrame
            |
            v
        MySQL etf
            |
            v
 goal_calculator ← housing.city_house_price
            |
            v
  etf_cagr / goal_down_payment → Redash
```

目前本機已跑通的是中間這段：`etf_to_mysql.py` 讀 `stock.etf_list`、抓 Yahoo、寫入 MySQL；`goal_calculator.py` 讀股價與六都總價，把試算寫回 MySQL。DAG 仍直接執行 `etf_to_mysql.py`，沒有把任務送進 RabbitMQ。

## 使用技術

| 技術 | 用途 |
| --- | --- |
| Python 3.11、uv | 程式開發與套件管理 |
| FinMind `TaiwanStockInfo` | 組員篩被動式 ETF 清單 |
| Yahoo Finance chart | 還原收盤、除權息、分割 |
| pandas、PyMySQL、MySQL | 試算與股價、房價儲存 |
| Celery、RabbitMQ | 任務派送程式已寫，尚未接上排程 |
| Docker Compose | MySQL、phpMyAdmin、抓價、Redash |
| Airflow | 交易日收盤後的 DAG，image 尚未換成自己的帳號 |
| Redash | 六都頭期款圖表 |

## 專案檔案

```text
etf-goal-calculator/
├── crawlers/
│   ├── etf/
│   │   ├── etf_to_mysql.py          # 讀清單、抓價、寫入 MySQL
│   │   ├── goal_calculator.py       # 報酬與頭期款試算
│   │   ├── etf_universe.py          # 清單表讀不到時的 FinMind 備援
│   │   ├── etf_producer.py          # 派送任務
│   │   ├── etf_tasks.py             # Celery 任務
│   │   ├── etf_worker.py            # Celery Worker
│   │   ├── etf_scheduler.py         # 尚未接上 Airflow 的定時更新
│   │   └── schema.sql               # etf 與 stock.etf_list 建表
│   ├── stock/                       # ETF 清單爬蟲，寫入 stock.etf_list
│   ├── housing/                     # 實價登錄、房價指數、CPI
│   └── finmind/                     # FinMind 日線爬蟲（獨立管線）
├── dags/etf_etl_dag.py              # 週一到週五 15:00
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml           # MySQL、phpMyAdmin、抓價
│   └── redash-compose.yml
├── swarm.yml
└── README.md
```

## 環境需求與設定

- Python 3.11、[uv](https://docs.astral.sh/uv/)
- Docker Engine／Docker Desktop 與 Docker Compose
- 可連線的 MySQL。本機 Compose 使用連接埠 `3306`
- 可存取 Yahoo Finance 與 FinMind 的網路

在 `crawlers/etf/` 安裝依賴：

```bash
uv sync
```

| 變數 | 預設 | 用途 |
| --- | --- | --- |
| `MYSQL_HOST`、`MYSQL_PORT` | `localhost`、`3306` | MySQL |
| `MYSQL_USER`、`MYSQL_PASSWORD` | `root`、空字串 | 帳號密碼。Compose 為 `root` / `rootpass` |
| `MYSQL_DB` | `etf` | 股價與試算結果 |
| `ETF_LIST_DB`、`ETF_LIST_TABLE` | `stock`、`etf_list` | 清單來源 |
| `HOUSING_DB` | `housing` | 六都總價 |
| `PRIMARY_ETF` | `0050` | 試算用的報酬率 |
| `DOWN_PAYMENT_RATIO` | `0.2` | 頭期款成數 |
| `INVEST_YEARS` | `10` | 投資年數 |
| `MONTHLY_INVEST` | `0` | 大於 0 時另算這筆金額十年後夠不夠 |
| `ETF_LIMIT` | 不設 | 只抓前 N 檔，用來試跑 |

## 執行方式

### 1. 啟動 MySQL、phpMyAdmin 與抓價

在專案根目錄：

```bash
docker compose -f docker/docker-compose.yml up --build
```

第一次啟動會載入 `crawlers/etf/schema.sql`。phpMyAdmin：http://localhost:8080 （`root` / `rootpass`）。

`stock.etf_list` 要先有資料，抓價才會用組員清單。清單程式在 `crawlers/stock`，寫入前需已有 `stock` 資料庫與 `etf_list` 表。

### 2. 重跑頭期款試算

MySQL 已在跑時，於專案根目錄：

```bash
docker compose -f docker/docker-compose.yml run --rm --no-deps -e MYSQL_PASSWORD=rootpass -e MONTHLY_INVEST=20000 -v "${PWD}/crawlers/etf/goal_calculator.py:/app/goal_calculator.py:ro" crawler uv run python goal_calculator.py
```

### 3. 開啟 Redash

```bash
docker compose -f docker/redash-compose.yml run --rm server create_db
docker compose -f docker/redash-compose.yml up -d
```

瀏覽器開 http://localhost:5000 ，第一次建立管理員帳號。

Settings → Data Sources → New Data Source → MySQL。

| 欄位 | 值 |
| --- | --- |
| Host | `host.docker.internal` |
| Port | `3306` |
| User | `root` |
| Password | `rootpass` |
| Database | `etf` |

查詢參數：`etf`（下拉，預設 `0050`）、`down_payment`（數字，預設 `0.2`）、`years`（數字，預設 `10`）、`monthly_invest`（數字，預設 `20000`）。下拉選項用 `SELECT stock_id FROM etf_cagr ORDER BY stock_id`。

```sql
SELECT
  p.city,
  p.median_total_wan AS house_price_wan,
  ROUND(p.median_total_wan * 10000 * {{down_payment}}) AS down_payment,
  c.stock_id,
  ROUND(c.cagr * 100, 2) AS cagr_pct,
  ROUND(
    (p.median_total_wan * 10000 * {{down_payment}})
    * (c.cagr / 12)
    / (POW(1 + c.cagr / 12, {{years}} * 12) - 1)
  ) AS monthly_needed,
  ROUND(
    {{monthly_invest}} * (POW(1 + c.cagr / 12, {{years}} * 12) - 1) / (c.cagr / 12)
  ) AS accumulated,
  CASE
    WHEN {{monthly_invest}} * (POW(1 + c.cagr / 12, {{years}} * 12) - 1) / (c.cagr / 12)
         >= p.median_total_wan * 10000 * {{down_payment}}
    THEN '可付' ELSE '不足'
  END AS can_pay
FROM housing.city_house_price p
JOIN etf_cagr c ON c.stock_id = '{{etf}}'
ORDER BY p.median_total_wan DESC
```

ETF 欄位先選到一檔再按 **Apply Changes**。Dashboard 用 Add Widget 掛上這支查詢，參數類型選 Dashboard。Publish 之後其他帳號才看得到。

## MySQL 資料與驗證

| 資料表 | 內容 | 寫入程式 |
| --- | --- | --- |
| `stock.etf_list` | 被動式 ETF 清單 | `crawlers/stock` |
| `etf.etf_price` | `date`、`stock_id`、`adj_close` | `etf_to_mysql.py` |
| `etf.etf_dividend`、`etf.etf_split` | 除權息、分割 | `etf_to_mysql.py` |
| `etf.etf_cagr` | 各檔含息年化報酬 | `goal_calculator.py` |
| `etf.goal_down_payment` | 六都頭期款與每月需投入 | `goal_calculator.py` |
| `housing.city_house_price` | 六都總價中位數（萬元） | 由實價登錄彙總後寫入 |
| `housing.housing_txn_qtr` | 六都單價與成交筆數 | `crawlers/housing` |
| `housing.housing_price_index`、`housing.cpi`、`housing.real_hpi` | 房價指數、CPI、實質房價指數 | `crawlers/housing` |

股價以 `stock_id` + `date` 更新同一筆。`housing_txn_qtr` 是元／平方公尺，試算不拿它當一戶總價。

```sql
SELECT stock_id, COUNT(*) AS row_count,
       MIN(`date`) AS first_date, MAX(`date`) AS last_date
FROM etf.etf_price
GROUP BY stock_id
ORDER BY stock_id;
```

```sql
SELECT city, house_price_wan, down_payment,
       primary_etf, monthly_needed_primary, computed_at
FROM etf.goal_down_payment
ORDER BY house_price_wan DESC;
```

```sql
SELECT city, median_total_wan, period
FROM housing.city_house_price
ORDER BY median_total_wan DESC;
```

## 開發進度與限制

| 項目 | 狀態 |
| --- | --- |
| `stock.etf_list` 與 Yahoo 抓價入庫 | 本機已寫入 MySQL |
| 六都總價與頭期款試算 | 已寫入 `goal_down_payment` |
| Redash 單一 ETF、頭期款、年數、每月投入 | 本機可操作 |
| Producer、Celery、RabbitMQ | 程式在 `crawlers/etf`，排程尚未改走這條 |
| Airflow DAG | 直接跑抓價 image；Docker Hub 帳號尚未決定 |
| 多檔權重組合 | 待討論 |

Yahoo 查無報價的代號會略過，不中斷整批。`city_house_price` 讀不到時，試算改用手填粗估，畫面上會註明。

## 參考資料

- `crawlers/finmind/README.md`：FinMind 日線管線自己的架構與課程操作。
- [FinMind API](https://finmindtrade.com/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [RabbitMQ Documentation](https://www.rabbitmq.com/docs)
- [uv Documentation](https://docs.astral.sh/uv/)

本專案用於資料工程學習與資料流程驗證，不構成投資建議。
