# FinMind ETF Price Crawler

使用 FinMind API 擷取台灣 ETF 歷史股價，透過 Python、Celery、RabbitMQ 與 MySQL 建立資料蒐集管線，作為後續 ETF 報酬分析、投資模擬與 Dashboard 的資料來源。

> **專案狀態：開發中。** 已有 FinMind 擷取、Celery 任務與 MySQL 寫入程式，並曾在課程環境完成單檔資料管線測試。多檔 ETF、去重複寫入、排程與完整 Docker 部署尚待整合驗證。本 README 不將課程範例的指令視為已驗證的一鍵安裝流程。

## 專案目的與資料範圍

- **資料來源**：FinMind API，`TaiwanStockPrice`。
- **初期標的**：0050、0056、006208（目前 Producer 實際只派送 0050）。
- **目標期間**：2016-01-01 至今；現有 Task 設定起始日，未指定結束日，實際回傳範圍以 API 為準。
- **資料內容**：`stock_id`、`date`、`open`、`max`、`min`、`close`、`Trading_Volume`、`Trading_money`、`spread` 等，以 API 實際欄位為準。
- **後續應用**：ETF 歷史走勢、定期定額模擬及投資與購屋能力分析。

本專案擷取的是**原始日線行情**，並非已還原配息、分割等公司行動的總報酬資料；若用於報酬率比較，須另行處理價格還原與配息。

## 系統架構

```text
[APScheduler：選用／待整合]
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
     FinMind API / TaiwanStockPrice
            |
            v
      pandas DataFrame
            |
            v
     SQLAlchemy → MySQL
```

Producer 送出指定 ETF 的爬取任務；RabbitMQ 負責傳遞任務；Celery Worker 呼叫 FinMind API，轉為 pandas DataFrame，並寫入 MySQL。排程器、不同 Queue 與去重複寫入已有課程範例，但尚未整合為統一的 ETF 正式執行流程。

## 使用技術

| 技術 | 用途 |
| --- | --- |
| Python 3.11、uv | 程式開發與套件管理 |
| FinMind API、Requests | 台股 ETF 歷史行情擷取 |
| pandas | API JSON 轉換與資料處理 |
| Celery、RabbitMQ | 非同步任務派送與執行 |
| SQLAlchemy、PyMySQL、MySQL | 資料庫連線與股價儲存 |
| Docker、Docker Compose | 容器化執行與服務管理 |
| APScheduler、Flower | 排程範例與 Worker 監控 |

## 專案檔案

```text
FinMind-etf-price-crawler/
├── crawler/
│   ├── config.py                            # 環境變數與連線設定
│   ├── worker.py                            # Celery App 與 Task 註冊
│   ├── producer_crawler_finmind.py          # 現行 0050 任務派送
│   ├── tasks_crawler_finmind.py             # 2016 起擷取，Append 寫入
│   ├── producer_crawler_finmind_duplicate.py
│   ├── tasks_crawler_finmind_duplicate.py   # Upsert 教學版本
│   ├── scheduler.py                         # APScheduler 範例
│   └── ...                                  # 其他課程範例
├── Dockerfile
├── docker-compose-worker.yml
├── docker-compose-worker-network.yml
├── docker-compose-worker-network-version.yml
├── docker-compose-producer-network.yml
├── docker-compose-producer-network-version.yml
├── docker-compose-producer-duplicate-network-version.yml
├── docker-compose-scheduler-network-version.yml
├── rabbitmq.yml
├── rabbitmq-network.yml
├── mysql.yml
├── pyproject.toml
├── uv.lock
├── docs/
│   └── course-notes.md                     # 原始課程操作筆記
└── README.md
```

以上列的是目前實際檔案與主要模組；保留多份 Compose 是因為它們對應不同的課程部署情境，**目前尚未選定單一正式版**。

## 環境需求與設定

- Python 3.11、[uv](https://docs.astral.sh/uv/)
- Docker Engine／Docker Desktop 與 Docker Compose（容器化執行時）
- 可用的 RabbitMQ 與 MySQL 服務
- 可存取 FinMind API 的網路環境

在專案根目錄安裝 Python 依賴：

```bash
uv sync --frozen
```

程式從 `crawler/config.py` 讀取 RabbitMQ 與 MySQL 設定。目前已確認使用的變數名稱包括：

| 變數 | 用途 |
| --- | --- |
| `RABBITMQ_HOST`、`RABBITMQ_PORT` | RabbitMQ 主機與埠號 |
| `WORKER_ACCOUNT`、`WORKER_PASSWORD` | RabbitMQ 帳號與密碼 |
| `MYSQL_HOST`、`MYSQL_PORT` | MySQL 主機與埠號 |
| `MYSQL_ACCOUNT`、`MYSQL_PASSWORD` | MySQL 帳號與密碼 |

請依照 `crawler/config.py` 的實際讀取方式配置環境變數。`.env` 不應提交 GitHub；本專案尚待補上可直接複製使用的 `.env.example`。請勿將真實密碼或含密碼的日誌貼到公開 Issue。

## 執行方式（目前的課程環境）

> **注意**：以下是現有檔案與程式可對應的操作方向，不是已驗證的全新環境一鍵啟動教學。Docker 網路、Image、環境變數、Queue 必須與執行環境一致。

### 1. 查看既有 Docker 服務

```bash
docker compose ls
docker ps
```

### 2. 使用既有 RabbitMQ／MySQL 環境

原始課程 README 使用以下設定檔：

```bash
# 僅供對照原始課程流程；執行前請確認網路、帳密、資料卷與連接埠
# docker network create my_network
# docker compose -f rabbitmq-network.yml up -d
# docker compose -f mysql.yml up -d
```

`rabbitmq-network.yml`、`mysql.yml` 的實際設定及前置條件請參閱 [`docs/course-notes.md`](docs/course-notes.md)。**不要在已有課程服務的環境直接重複啟動另一套同名或同埠服務。**

### 3. 手動派送 ETF 股價任務

目前 `crawler/producer_crawler_finmind.py` 實際派送 `0050`，使用預設 Celery Queue：

```bash
uv run python -m crawler.producer_crawler_finmind
```

派送前必須確認 RabbitMQ 可連線、Worker 已啟動，且 Worker 正在監聽該任務所使用的 Queue。**派送成功不代表資料已寫入成功。**

目前 `docker-compose-worker-network.yml` 的兩個 Worker 僅監聽 `twse`、`tpex` Queue；但上述 Producer 使用 `.delay()`，若沒有其他路由設定，預設送至 `celery` Queue。因此不能直接假設這兩者可搭配執行。請先核對 Queue 設定，再執行正式測試。

### 4. 查看 Worker 執行結果

在你實際啟動 Worker 的環境查看對應日誌，確認是否出現任務接收、FinMind 資料取得及資料庫寫入相關訊息。若使用 Docker Compose，可先用：

```bash
docker compose ps
```

再依實際使用的 Compose 檔案與服務名稱查看 Log。不要只依據 Celery 的 `succeeded` 判定資料庫寫入成功：目前 Append 版寫入函式會捕捉例外並印出，可能未向上回報失敗。

## MySQL 資料與驗證

目前有兩種寫入方式：

| Task | 資料表 | 日期設定 | 寫入方式 |
| --- | --- | --- | --- |
| `crawler_finmind` | `mydb.TaiwanStockPrice` | 自 2016-01-01 | `append`；重跑可能重複 |
| `crawler_finmind_duplicate` | `mydb.TaiwanStockPrice_duplicate` | 2024-01-01 至 2025-06-17 | `stock_id` + `date` 複合主鍵 Upsert |

兩者**寫入不同資料表**，不要將 Upsert 範例誤認為已保護原始 `TaiwanStockPrice` 表。Upsert 範例的日期尚未符合本專題目標，且其資料表不會自動替已存在的舊表補上主鍵。

在已登入並具有查詢權限的 MySQL／phpMyAdmin 執行以下**唯讀 SQL**：

```sql
SELECT stock_id, COUNT(*) AS row_count,
       MIN(date) AS first_date, MAX(date) AS last_date
FROM mydb.TaiwanStockPrice
GROUP BY stock_id
ORDER BY stock_id;
```

檢查同股票同日期是否重複：

```sql
SELECT stock_id, date, COUNT(*) AS duplicate_count
FROM mydb.TaiwanStockPrice
GROUP BY stock_id, date
HAVING COUNT(*) > 1
LIMIT 20;
```

查看最近資料：

```sql
SELECT stock_id, date, open, max, min, close, Trading_Volume
FROM mydb.TaiwanStockPrice
ORDER BY date DESC
LIMIT 10;
```

若表格尚未建立，查詢會失敗；請先確認 MySQL 連線、資料庫與實際表名。不要為了驗證而清空既有資料。

## 開發進度與限制

| 項目 | 狀態 |
| --- | --- |
| FinMind `TaiwanStockPrice` 擷取 | 已有程式 |
| 0050 Producer 派送 | 已設定；課程環境曾完成管線測試 |
| 0056、006208 多檔派送 | 待整合 |
| 2016 年至今股價資料 | Append Task 已設定起始日；完整資料仍需查詢驗證 |
| MySQL Append 寫入 | 已有程式，重複執行有重複列風險 |
| MySQL Upsert | 已有獨立範例，待整合日期與正式資料表 |
| Scheduler | 已有課程範例，尚未確認正式部署 |
| Docker 一鍵部署 | 待整理與端到端驗證 |
| Dashboard／投資分析 | 後續階段 |

**已知限制**：FinMind API 可能有請求限制、資料更新時間及欄位變動；程式目前未完整檢查 API 業務狀態、空資料及寫入錯誤回報。原始價格不能直接當作含息總報酬。使用者應自行確認資料完整性與適用性。

## 課程操作筆記與參考資料

- [原始課程操作筆記](docs/course-notes.md)：Docker Compose、Celery、RabbitMQ、MySQL、GCP、BigQuery 等進階操作。
- [FinMind API](https://finmindtrade.com/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [RabbitMQ Documentation](https://www.rabbitmq.com/docs)
- [uv Documentation](https://docs.astral.sh/uv/)

本專案用於資料工程學習與資料流程驗證，不構成投資建議。
