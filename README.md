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
| `crawlers/etf/goal_calculator.py` | 用 `etf_price` 算含息報酬，讀 `housing.city_house_price` 試算頭期款 |
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
- 六都房價：`housing.city_house_price.median_total_wan`（萬元）。沒有這張表時，試算改用手填粗估。

## 看試算結果

Docker 起來後，瀏覽器開 http://localhost:8080（帳號 `root`，密碼 `rootpass`）。

- 資料庫 `etf`、表 `goal_down_payment`：每個城市一列。`house_price_wan` 是房價（萬元），`down_payment` 是頭期款（元），`monthly_needed_primary` 是依所選 ETF 報酬每月要存的金額。
- 資料庫 `housing`、表 `city_house_price`：六都成交總價中位數。`goal_calculator.py` 讀這一欄。

重跑試算（在專案根目錄，MySQL 已在跑）：

```bash
docker compose -f docker/docker-compose.yml run --rm --no-deps -e MONTHLY_INVEST=20000 -v "${PWD}/crawlers/etf/goal_calculator.py:/app/goal_calculator.py:ro" crawler uv run python goal_calculator.py
```

## Redash

圖表服務和 ETF 的 MySQL 分開。在專案根目錄：

```bash
docker compose -f docker/redash-compose.yml run --rm server create_db
docker compose -f docker/redash-compose.yml up -d
```

瀏覽器開 http://localhost:5000。第一次會要求建立管理員帳號。

### 接上 MySQL

Settings → Data Sources → New Data Source → MySQL。

| 欄位 | 值 |
|------|-----|
| Host | `host.docker.internal` |
| Port | `3306` |
| User | `root` |
| Password | `rootpass` |
| Database | `etf` |

### 建立試算查詢

Create → Query，資料來源選剛建的 MySQL。加上四個參數：`etf`（下拉，預設 `0050`）、`down_payment`（數字，預設 `0.2`）、`years`（數字，預設 `10`）、`monthly_invest`（數字，預設 `20000`）。`etf` 的選項用另一支查詢 `SELECT stock_id FROM etf_cagr ORDER BY stock_id`。

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

改完參數按 **Apply Changes**。ETF 欄位要先選到一檔再按，空白會失敗。**Table** 是數字，**每月需投入** 是長條圖。

### Dashboard

1. Create → Dashboard，輸入名稱後存檔。
2. 右上 Refresh 旁邊的箭頭 → Add Widget。
3. 選上面的查詢，再選長條圖或 Table。參數類型選 Dashboard，四個條件才會出現在儀表板最上面。
4. 改 ETF、頭期款比例、年數、每月投入後按 Apply Changes。
5. Publish 之後，其他登入帳號才看得到。
