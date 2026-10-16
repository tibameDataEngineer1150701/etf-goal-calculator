# 目標試算：ETF 報酬 + 六都房價 → 「每月投入 X → 10 年後能否付頭期款」
# 資料來源：
#   - ETF 報酬：讀本專案 MySQL 的 etf_price（adj_close）→ 算含息年化報酬 CAGR
#   - 六都房價：目前用「參數」帶入（等組員 rchingyun 的實價登錄金額出來再填）
# 只用課程教過的基本寫法（for/if、無型別標註），方便看懂。
#
# 用法：
#   export MYSQL_HOST=localhost MYSQL_USER=帳號 MYSQL_PASSWORD=密碼 MYSQL_DB=etf
#   export MONTHLY_INVEST=20000        # （可選）每月投入元；不設就只算「需要投入多少」
#   uv run python goal_calculator.py

import os
import datetime
import pandas as pd
import pymysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("MYSQL_DB", "etf")

# ── 參數（可用環境變數覆蓋）──
DOWN_PAYMENT_RATIO = float(os.environ.get("DOWN_PAYMENT_RATIO", "0.2"))   # 頭期款成數（預設 2 成）
YEARS = int(os.environ.get("INVEST_YEARS", "10"))                         # 投資年數
MONTHLY_INVEST = float(os.environ.get("MONTHLY_INVEST", "0"))             # 每月投入(元)；0=只算需要多少
CONSERVATIVE_RETURN = float(os.environ.get("CONSERVATIVE_RETURN", "0.07"))  # 保守年化報酬(對照用)

# ⚠ 六都房價（總價，單位：萬元）——目前為「粗估佔位值」，
#    請改成組員 rchingyun 實價登錄分析出來的實際數字！
SIX_CITIES_PRICE_WAN = {
    "台北市": 2500,
    "新北市": 1500,
    "桃園市": 1000,
    "台中市": 1300,
    "台南市": 850,
    "高雄市": 1000,
}

# 用哪一檔 ETF 的報酬率當主要試算依據（找不到就用所有 ETF 的中位數）
PRIMARY_ETF = os.environ.get("PRIMARY_ETF", "0050")


def get_conn():
    return pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                           password=MYSQL_PASSWORD, database=MYSQL_DB, charset="utf8mb4")


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

    print(f"\n=== 六都：每月需投入多少，{YEARS} 年後能付頭期款 ===")
    header = f"{'城市':<6}{'房價(萬)':>8}{'頭期款(萬)':>10}{'每月需投入@' + name:>16}{'每月需投入@保守':>16}"
    print(header)
    city_rows = []
    for city, price_wan in SIX_CITIES_PRICE_WAN.items():
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
        for city, price_wan in SIX_CITIES_PRICE_WAN.items():
            target = price_wan * 10000 * DOWN_PAYMENT_RATIO
            ok_main = "可付" if fv_main >= target else "不足"
            ok_cons = "可付" if fv_cons >= target else "不足"
            print(f"  {city}：頭期款 {target:,.0f} 元 → @{name} {ok_main} / @保守 {ok_cons}")

    print("\n⚠ 六都房價為佔位參數，請改成 rchingyun 實價登錄的實際數字（程式最上方 SIX_CITIES_PRICE_WAN）。")


if __name__ == "__main__":
    main()
