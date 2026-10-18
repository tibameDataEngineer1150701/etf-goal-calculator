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

先裝好 Docker Desktop、Python 3.11 和 [uv](https://docs.astral.sh/uv/)。**3306**、**8080**、**5000** 要是空的。不要另外啟動 `crawlers/housing` 或 `crawlers/finmind` 裡的 `mysql.yml`，那兩個檔也會佔用 3306。

下面指令在專案根目錄執行。第 3 步要先進入 `crawlers/stock`。

### 1. 下載專案

Clone 只會拿到程式。股價、ETF 清單和 Redash 圖表都在各自的資料庫裡，不會跟著 Git 下來。

```bash
git clone https://github.com/tibameDataEngineer1150701/etf-goal-calculator.git
cd etf-goal-calculator
```

### 2. 先啟動 MySQL 和 phpMyAdmin

這一步只開資料庫和看資料的網頁，先不抓股價。第一次啟動會執行 `crawlers/etf/schema.sql`，建好 `etf` 的表、空的 `stock.etf_list`，以及 `housing.city_house_price` 的 2026Q3 六都總價。

空的清單去抓價不會寫進任何一檔。所以等清單寫入之後，再做第 4 步。

```bash
docker compose -f docker/docker-compose.yml up -d --build mysql phpmyadmin
```

瀏覽器開 http://localhost:8080 ，帳號 `root`，密碼 `rootpass`。看得到 `etf`、`stock`、`housing` 就代表這一步完成。

### 3. 把 ETF 清單寫進 MySQL

抓價程式讀的是 `stock.etf_list` 的 `stock_id` 和 `market`。這支程式在 `crawlers/stock`，會向 FinMind 要清單、篩掉主動式和槓桿反向，再寫進 MySQL。它預設連 3307，所以要用環境變數改到本機這套 MySQL。

```bash
cd crawlers/stock
uv sync
export MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_USER=root MYSQL_DATABASE=stock
uv run python -m crawler.save_etf_list
```

畫面上問密碼時輸入 `rootpass`。完成後約 279 筆，`market` 為 `twse` 或 `tpex`。PowerShell 把 `export ...` 換成：

```powershell
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_PORT = "3306"
$env:MYSQL_USER = "root"
$env:MYSQL_DATABASE = "stock"
```

### 4. 抓股價寫進 `etf.etf_price`

回到專案根目錄。這一支會依清單逐檔問 Yahoo，上市用 `.TW`、上櫃用 `.TWO`，把還原收盤、除權息和分割寫進 `etf`。全清單會跑很久；想先確認流程，用下面註解那行只抓 15 檔。

```bash
cd ../..
docker compose -f docker/docker-compose.yml run --rm crawler
# docker compose -f docker/docker-compose.yml run --rm -e ETF_LIMIT=15 crawler
```

Yahoo 查無報價的代號會略過，不中斷整批。跑完可在 phpMyAdmin 看 `etf.etf_price` 有沒有列。

### 5. 跑頭期款試算

試算讀 `etf.etf_price` 算各檔年化報酬，讀 `housing.city_house_price` 當六都總價，把每月需投入寫進 `etf.goal_down_payment`。`goal_calculator.py` 不在抓價 image 裡，所以用掛載把程式放進容器。

目前表上是 2026Q3 的中位數。若 `crawlers/housing/crawler/extracted` 已有更新的一季成交檔，這次執行會重算總價中位數再寫回；沒有新檔就維持 2026Q3。第二個掛載就是把那個目錄給試算程式看。`housing_txn_qtr` 是每平方公尺單價，不會拿來換算一戶總價。

`MONTHLY_INVEST=20000` 表示另外試算「每月存 2 萬、10 年後夠不夠付頭期款」。只想看每月要存多少時，可以把這個環境變數拿掉。

```bash
docker compose -f docker/docker-compose.yml run --rm --no-deps -e MYSQL_PASSWORD=rootpass -e MONTHLY_INVEST=20000 -v "${PWD}/crawlers/etf/goal_calculator.py:/app/goal_calculator.py:ro" -v "${PWD}/crawlers/housing/crawler/extracted:/housing/crawler/extracted:ro" crawler uv run python goal_calculator.py
```

結果在 phpMyAdmin 的 `etf.etf_cagr` 和 `etf.goal_down_payment`。

### 6. 開啟 Redash

圖表服務用自己的資料庫，和 ETF 的 MySQL 分開，所以要另外啟動。`create_db` 只在第一次建立 Redash 自己的表；之後只要 `up -d`。

```bash
docker compose -f docker/redash-compose.yml run --rm server create_db
docker compose -f docker/redash-compose.yml up -d
```

瀏覽器開 http://localhost:5000 ，第一次自己建立管理員帳號。

接著把 ETF 的 MySQL 接進來：Settings → Data Sources → New Data Source → MySQL。Host 填 `host.docker.internal`，因為 Redash 在容器裡，`localhost` 指的是它自己，不是你電腦上的 MySQL。

| 欄位 | 值 |
| --- | --- |
| Host | `host.docker.internal` |
| Port | `3306` |
| User | `root` |
| Password | `rootpass` |
| Database | `etf` |

Create → Query，資料來源選剛建的 MySQL。這支查詢用畫面上的四個參數重算頭期款，不用改程式：`etf`（下拉，預設 `0050`）、`down_payment`（頭期款成數，預設 `0.2`）、`years`（年數，預設 `10`）、`monthly_invest`（每月投入，預設 `20000`）。ETF 下拉的選項要先另存一支查詢 `SELECT stock_id FROM etf_cagr ORDER BY stock_id`，而且要先執行過一次，下拉才有資料。

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

存檔後先在 ETF 欄選到一檔，再按 **Apply Changes**。空白送出會因為沒有 ETF 參數而失敗。Table 是數字，長條圖用「每月需投入」。

做成儀表板：Create → Dashboard，取名後存檔。右上 Refresh 旁的箭頭 → Add Widget，選這支查詢和圖或表。參數類型要選 Dashboard，四個條件才會出現在儀表板上方。改完按 Apply Changes。Publish 之後，其他登入帳號才看得到。

## MySQL 資料與驗證

| 資料表 | 內容 | 寫入程式 |
| --- | --- | --- |
| `stock.etf_list` | 被動式 ETF 清單 | `crawlers/stock` |
| `etf.etf_price` | `date`、`stock_id`、`adj_close` | `etf_to_mysql.py` |
| `etf.etf_dividend`、`etf.etf_split` | 除權息、分割 | `etf_to_mysql.py` |
| `etf.etf_cagr` | 各檔含息年化報酬 | `goal_calculator.py` |
| `etf.goal_down_payment` | 六都頭期款與每月需投入 | `goal_calculator.py` |
| `housing.city_house_price` | 六都總價中位數（萬元）。目前種子是 2026Q3 | 試算時若 `crawlers/housing/crawler/extracted` 有更新的一季，會重算並覆蓋 |
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

Yahoo 查無報價的代號會略過，不中斷整批。`city_house_price` 連不上 MySQL 時，試算才改用手填粗估，畫面上會註明。

## 參考資料

- `crawlers/finmind/README.md`：FinMind 日線管線自己的架構與課程操作。
- [FinMind API](https://finmindtrade.com/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [RabbitMQ Documentation](https://www.rabbitmq.com/docs)
- [uv Documentation](https://docs.astral.sh/uv/)

本專案用於資料工程學習與資料流程驗證，不構成投資建議。
