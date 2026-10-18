# 目標試算：ETF 報酬 + 六都房價 → 「每月投入 X → 10 年後能否付頭期款」
# 資料來源：
#   - ETF 報酬：讀本專案 MySQL 的 etf_price（adj_close）→ 算含息年化報酬 CAGR
#   - 六都房價：讀 MySQL housing.city_house_price。
#     若組員爬蟲有解壓更新的一季成交檔，先重算總價中位數再寫回這張表。
#
# 用法：
#   export MYSQL_HOST=localhost MYSQL_USER=帳號 MYSQL_PASSWORD=密碼 MYSQL_DB=etf
#   export MONTHLY_INVEST=20000        # （可選）每月投入元；不設就只算「需要投入多少」
#   uv run python goal_calculator.py

import os
import datetime
from pathlib import Path
import pandas as pd
import pymysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("MYSQL_DB", "etf")
HOUSING_DB = os.environ.get("HOUSING_DB", "housing")

# ── 參數（可用環境變數覆蓋）──
DOWN_PAYMENT_RATIO = float(os.environ.get("DOWN_PAYMENT_RATIO", "0.2"))   # 頭期款成數（預設 2 成）
YEARS = int(os.environ.get("INVEST_YEARS", "10"))                         # 投資年數
MONTHLY_INVEST = float(os.environ.get("MONTHLY_INVEST", "0"))             # 每月投入(元)；0=只算需要多少
CONSERVATIVE_RETURN = float(os.environ.get("CONSERVATIVE_RETURN", "0.07"))  # 保守年化報酬(對照用)

# 讀不到 housing.city_house_price 時才用的粗估（總價，萬元）
FALLBACK_CITY_PRICE_WAN = {
    "台北市": 2500,
    "新北市": 1500,
    "桃園市": 1000,
    "台中市": 1300,
    "台南市": 850,
    "高雄市": 1000,
}

# 用哪一檔 ETF 的報酬率當主要試算依據（找不到就用所有 ETF 的中位數）
PRIMARY_ETF = os.environ.get("PRIMARY_ETF", "0050")


def get_conn(database=None):
    return pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                           password=MYSQL_PASSWORD, database=database or MYSQL_DB, charset="utf8mb4")


# 2026Q3 六都住宅成交總價中位數。與 schema.sql 同一份，表是空的就補上。
CITY_HOUSE_PRICE_SEED = [
    ("台中市", 10403, 14850000, "2026Q3", 1485),
    ("台北市", 5851, 28700000, "2026Q3", 2870),
    ("台南市", 5126, 10850000, "2026Q3", 1085),
    ("新北市", 13486, 16680000, "2026Q3", 1668),
    ("桃園市", 12123, 12610000, "2026Q3", 1261),
    ("高雄市", 8658, 10895000, "2026Q3", 1090),
]


# 組員成交檔的縣市代碼（檔名第一個字母）。只在我們這邊用來挑檔。
CITY_FILE_CODE = {
    "a": "台北市", "f": "新北市", "h": "桃園市",
    "b": "台中市", "d": "台南市", "e": "高雄市",
}
RESIDENTIAL_TYPES = {"房地(土地+建物)", "房地(土地+建物)+車位"}


def housing_extracted_roots():
    # 組員爬蟲把實價登錄解壓在 crawlers/housing/crawler/extracted/115S3 這種目錄。
    roots = []
    configured = os.environ.get("HOUSING_EXTRACTED")
    if configured:
        roots.append(Path(configured))
    roots.append(Path(__file__).resolve().parents[1] / "housing" / "crawler" / "extracted")
    roots.append(Path("/housing/crawler/extracted"))
    return roots


def season_sort_key(name):
    year, quarter = name.split("S", 1)
    return (int(year), int(quarter))


def season_to_period(name):
    year, quarter = season_sort_key(name)
    return f"{year + 1911}Q{quarter}"


def latest_extracted_season():
    seasons = []
    for root in housing_extracted_roots():
        if not root.is_dir():
            continue
        for folder in root.iterdir():
            if not folder.is_dir() or "S" not in folder.name:
                continue
            year = folder.name.split("S", 1)[0]
            if year.isdigit():
                seasons.append(folder)
    if not seasons:
        return None
    return max(seasons, key=lambda folder: season_sort_key(folder.name))


def median_rows_from_season(season_dir):
    # 住宅成交、總價大於 0，取各市總價中位數。
    frames = []
    for path in season_dir.glob("*_lvr_land_[ab].csv"):
        city = CITY_FILE_CODE.get(path.name[0].lower())
        if city is None:
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, skiprows=[1],
                            usecols=["交易標的", "總價元"])
        frame = frame[frame["交易標的"].isin(RESIDENTIAL_TYPES)]
        frame["總價元"] = pd.to_numeric(frame["總價元"], errors="coerce")
        frame = frame[frame["總價元"] > 0]
        if frame.empty:
            continue
        frame["city"] = city
        frames.append(frame[["city", "總價元"]])
    if not frames:
        return []
    combined = pd.concat(frames, ignore_index=True)
    grouped = combined.groupby("city")["總價元"]
    period = season_to_period(season_dir.name)
    rows = []
    for city, series in grouped:
        median_yuan = int(round(float(series.median())))
        rows.append((city, int(series.size), median_yuan, period, int(round(median_yuan / 10000))))
    return rows


def refresh_city_house_price():
    # 有最新一季成交檔就重算並覆蓋；沒有檔，或檔比表上的季別舊，就維持現值。
    season = latest_extracted_season()
    if season is None:
        print("沒有新的成交檔，六都中位數維持資料庫現值")
        return
    rows = median_rows_from_season(season)
    if not rows:
        print(f"{season.name} 沒有六都住宅成交，六都中位數維持資料庫現值")
        return
    period = rows[0][3]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(period) FROM housing.city_house_price")
            current = cur.fetchone()[0]
            if current and period < str(current):
                print(f"成交檔 {season.name}（{period}）比資料庫 {current} 舊，不覆蓋")
                return
            for city, count, median_yuan, row_period, median_wan in rows:
                cur.execute("DELETE FROM housing.city_house_price WHERE city=%s", (city,))
                cur.execute(
                    "INSERT INTO housing.city_house_price "
                    "(city, transaction_count, median_total_yuan, period, median_total_wan) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (city, count, median_yuan, row_period, median_wan))
        conn.commit()
    finally:
        conn.close()
    print(f"已用 {season.name} 更新 {len(rows)} 個城市的總價中位數（{period}）")


def ensure_city_house_price():
    # 建庫建表。表是空的才寫入 2026Q3，之後改由成交檔覆蓋。
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS housing "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS housing.city_house_price ("
                " city VARCHAR(16) NOT NULL,"
                " transaction_count BIGINT,"
                " median_total_yuan BIGINT,"
                " period VARCHAR(16),"
                " median_total_wan INT,"
                " PRIMARY KEY (city))")
            cur.execute("SELECT COUNT(*) FROM housing.city_house_price")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    "INSERT INTO housing.city_house_price "
                    "(city, transaction_count, median_total_yuan, period, median_total_wan) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    CITY_HOUSE_PRICE_SEED)
        conn.commit()
    finally:
        conn.close()


def load_city_prices():
    # 先依最新成交檔更新中位數，再從 MySQL 讀。housing_txn_qtr 是單價，不用來換算總價。
    ensure_city_house_price()
    refresh_city_house_price()
    sql = "SELECT city, median_total_wan, period FROM city_house_price"
    try:
        conn = get_conn(HOUSING_DB)
        frame = pd.read_sql(sql, conn)
        conn.close()
    except Exception as err:
        print(f"讀不到 {HOUSING_DB}.city_house_price（{err}），改用手填粗估房價")
        return FALLBACK_CITY_PRICE_WAN, None
    if frame.empty:
        print(f"{HOUSING_DB}.city_house_price 沒有資料，改用手填粗估房價")
        return FALLBACK_CITY_PRICE_WAN, None
    period = str(frame["period"].iloc[0])
    prices = {str(row.city): int(row.median_total_wan) for row in frame.itertuples()}
    print(f"六都房價：{period}（{HOUSING_DB}.city_house_price）")
    return prices, period


def load_etf_prices():
    # 從 etf_price 讀回 (date, stock_id, adj_close)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("select `date`, stock_id, adj_close from etf_price")
            rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=["date", "stock_id", "adj_close"])
    df["adj_close"] = df["adj_close"].astype(float)      # Decimal → float
    return df


def etf_cagr(prices):
    # 每檔 ETF 的含息年化報酬 CAGR（用還原收盤 adj_close）
    result = {}
    for sid in prices["stock_id"].unique():
        d = prices[prices["stock_id"] == sid].sort_values("date")
        if len(d) < 240:                                 # 資料太少（不到約一年）就略過
            continue
        start = d["adj_close"].iloc[0]
        end = d["adj_close"].iloc[-1]
        years = (pd.to_datetime(d["date"].iloc[-1]) - pd.to_datetime(d["date"].iloc[0])).days / 365
        if years < 1 or start <= 0:
            continue
        result[sid] = (end / start) ** (1 / years) - 1
    return result


def future_value_monthly(monthly, annual_return, years):
    # 定期定額終值：每月投入 monthly、年化 annual_return、years 年
    i = annual_return / 12
    n = years * 12
    if i == 0:
        return monthly * n
    return monthly * (((1 + i) ** n - 1) / i)


def monthly_needed(target, annual_return, years):
    # 反推：要在 years 年累積到 target，每月需投入多少
    i = annual_return / 12
    n = years * 12
    if i == 0:
        return target / n
    return target * i / ((1 + i) ** n - 1)


def pick_return(cagr):
    # 選主要試算用的報酬率：優先 PRIMARY_ETF，否則用所有 ETF 的中位數
    if PRIMARY_ETF in cagr:
        return PRIMARY_ETF, cagr[PRIMARY_ETF]
    if cagr:
        values = sorted(cagr.values())
        median = values[len(values) // 2]
        return "中位數", median
    return None, None


def save_results(cagr, city_rows):
    # 把結果寫回 MySQL（etf_cagr、goal_down_payment），給 Redash 畫 dashboard
    now = datetime.datetime.now()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cagr_rows = [(sid, round(cagr[sid], 5), now) for sid in cagr]
            cur.executemany(
                "insert into etf_cagr (stock_id, cagr, computed_at) values (%s,%s,%s) "
                "on duplicate key update cagr=values(cagr), computed_at=values(computed_at)",
                cagr_rows)
            cur.executemany(
                "insert into goal_down_payment "
                "(city, house_price_wan, down_payment, primary_etf, primary_return, "
                " monthly_needed_primary, monthly_needed_conservative, computed_at) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s) "
                "on duplicate key update house_price_wan=values(house_price_wan), "
                "down_payment=values(down_payment), primary_etf=values(primary_etf), "
                "primary_return=values(primary_return), "
                "monthly_needed_primary=values(monthly_needed_primary), "
                "monthly_needed_conservative=values(monthly_needed_conservative), "
                "computed_at=values(computed_at)",
                [row + (now,) for row in city_rows])     # 每列補上 computed_at
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    prices = load_etf_prices()
    if len(prices) == 0:
        print("etf_price 沒有資料，請先跑 etf_to_mysql.py 把股價寫進 MySQL")
        return

    cagr = etf_cagr(prices)
    print("=== 各 ETF 含息年化報酬(CAGR) ===")
    for sid in sorted(cagr):
        print(f"  {sid}: {cagr[sid] * 100:.2f}% /年")

    name, r = pick_return(cagr)
    if r is None:
        print("沒有足夠的 ETF 報酬資料")
        return
    print(f"\n主要試算報酬率：用 {name} = {r * 100:.2f}% /年（另附保守 {CONSERVATIVE_RETURN * 100:.0f}% 對照）")
    print(f"頭期款成數 {DOWN_PAYMENT_RATIO:.0%}、投資 {YEARS} 年")

    city_prices, price_period = load_city_prices()
    print(f"\n=== 六都：每月需投入多少，{YEARS} 年後能付頭期款 ===")
    header = f"{'城市':<6}{'房價(萬)':>8}{'頭期款(萬)':>10}{'每月需投入@' + name:>16}{'每月需投入@保守':>16}"
    print(header)
    city_rows = []
    for city, price_wan in city_prices.items():
        target = price_wan * 10000 * DOWN_PAYMENT_RATIO          # 萬元→元 ×成數
        need_main = monthly_needed(target, r, YEARS)
        need_cons = monthly_needed(target, CONSERVATIVE_RETURN, YEARS)
        print(f"{city:<6}{price_wan:>8}{price_wan * DOWN_PAYMENT_RATIO:>10.0f}"
              f"{need_main:>16,.0f}{need_cons:>16,.0f}")
        city_rows.append((city, price_wan, int(target), name, round(r, 5),
                          int(need_main), int(need_cons)))

    # 寫回 MySQL，給 Redash 用（computed_at 由 save_results 自動補上）
    save_results(cagr, city_rows)
    print("\n已把結果寫回 MySQL：etf_cagr、goal_down_payment（可用 Redash 畫 dashboard）")

    if MONTHLY_INVEST > 0:
        fv_main = future_value_monthly(MONTHLY_INVEST, r, YEARS)
        fv_cons = future_value_monthly(MONTHLY_INVEST, CONSERVATIVE_RETURN, YEARS)
        print(f"\n=== 若每月投入 {MONTHLY_INVEST:,.0f} 元，{YEARS} 年後能否付頭期款？ ===")
        print(f"  {YEARS} 年後累積：@{name} {fv_main:,.0f} 元 / @保守 {fv_cons:,.0f} 元")
        for city, price_wan in city_prices.items():
            target = price_wan * 10000 * DOWN_PAYMENT_RATIO
            ok_main = "可付" if fv_main >= target else "不足"
            ok_cons = "可付" if fv_cons >= target else "不足"
            print(f"  {city}：頭期款 {target:,.0f} 元 → @{name} {ok_main} / @保守 {ok_cons}")

    if price_period is None:
        print("\n六都房價用的是手填粗估，不是實價登錄。")


if __name__ == "__main__":
    main()
