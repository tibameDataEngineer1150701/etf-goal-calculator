# 把「被動式 ETF」的股價 / 除權息 / 分割 寫進 MySQL（三張表都寫）
# 流程：etf_universe(全台股→ETF→被動式) → 逐檔 Yahoo 抓價(依市場給後綴) → 寫入 MySQL
# 只用課程教過的基本寫法（普通 for 迴圈、if/else、無型別標註），方便看懂。
# 對應課程：05(API+JSON)、07(pandas)、17(交易 commit/rollback)、20(PyMySQL)
#
# 用法：
#   uv sync
#   mysql etf < schema.sql
#   export MYSQL_HOST=localhost MYSQL_USER=你的帳號 MYSQL_PASSWORD=你的密碼 MYSQL_DB=etf
#   export ETF_LIMIT=15                 # （可選）先小量測試
#   uv run python etf_to_mysql.py

import os
import json
import time
import datetime
import urllib.request
import pandas as pd
import pymysql
from etf_universe import get_passive_etf_list

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ── 資料庫連線設定：從環境變數讀，不要把密碼寫死（course 20 安全提醒）──
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("MYSQL_DB", "etf")


def get_conn():
    return pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                           password=MYSQL_PASSWORD, database=MYSQL_DB, charset="utf8mb4")


def get_date_text(unix_seconds):
    # Unix 秒數 → '2026-10-02' 這種文字
    d = datetime.datetime.fromtimestamp(unix_seconds, datetime.timezone.utc)
    return d.strftime("%Y-%m-%d")


def fetch_chart(stock_id, market):
    # 上市 twse → .TW；上櫃 tpex → .TWO（很多債券 ETF 在上櫃）
    if market == "twse":
        suffix = ".TW"
    else:
        suffix = ".TWO"
    symbol = stock_id + suffix
    period2 = int(time.time())
    period1 = period2 - 60 * 60 * 24 * 365 * 12        # 抓 12 年
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={period1}&period2={period2}&interval=1d&events=div,split"
    request = urllib.request.Request(url, headers=HEADERS)
    response = urllib.request.urlopen(request, timeout=30)
    return json.loads(response.read())


def parse_prices(stock_id, data):
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    adj_close_list = result["indicators"]["adjclose"][0]["adjclose"]
    rows = []
    for i in range(len(timestamps)):
        price = adj_close_list[i]
        if price is None:               # 非交易日/停牌沒有價格 → 跳過
            continue
        rows.append({"date": get_date_text(timestamps[i]), "stock_id": stock_id, "adj_close": price})
    return pd.DataFrame(rows)


def parse_dividends(stock_id, data):
    result = data["chart"]["result"][0]
    rows = []
    if "events" in result and "dividends" in result["events"]:
        dividends = result["events"]["dividends"]
        for key in dividends:
            item = dividends[key]
            rows.append({"stock_id": stock_id, "ex_date": get_date_text(item["date"]), "amount": item["amount"]})
    return pd.DataFrame(rows)


def parse_splits(stock_id, data):
    result = data["chart"]["result"][0]
    rows = []
    if "events" in result and "splits" in result["events"]:
        splits = result["events"]["splits"]
        for key in splits:
            item = splits[key]
            rows.append({"stock_id": stock_id, "split_date": get_date_text(item["date"]),
                         "numerator": item["numerator"], "denominator": item["denominator"], "ratio": item["splitRatio"]})
    return pd.DataFrame(rows)


def save(df, sql):
    # 共用寫入：批次寫入 + 交易保護
    if df is None or len(df) == 0:
        return 0
    rows = df.where(df.notna(), None).to_dict("records")    # 把 NaN 換成 None
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executemany(sql, rows)      # 一次寫很多筆，比一筆筆快
        conn.commit()                   # 異動一定要 commit
        return len(rows)
    except Exception:
        conn.rollback()                 # 出錯就還原，避免寫一半
        raise
    finally:
        conn.close()                    # 不論成敗都關連線


def save_prices(df):
    sql = ("insert into etf_price (`date`, stock_id, adj_close) "
           "values (%(date)s, %(stock_id)s, %(adj_close)s) "
           "on duplicate key update adj_close = values(adj_close)")   # 有就更新、沒有就新增
    return save(df, sql)


def save_dividends(df):
    sql = ("insert into etf_dividend (stock_id, ex_date, amount) "
           "values (%(stock_id)s, %(ex_date)s, %(amount)s) "
           "on duplicate key update amount = values(amount)")
    return save(df, sql)


def save_splits(df):
    sql = ("insert into etf_split (stock_id, split_date, numerator, denominator, ratio) "
           "values (%(stock_id)s, %(split_date)s, %(numerator)s, %(denominator)s, %(ratio)s) "
           "on duplicate key update numerator=values(numerator), denominator=values(denominator), ratio=values(ratio)")
    return save(df, sql)


def main():
    etfs = get_passive_etf_list()       # [{stock_id, stock_name, market}, ...]

    limit = os.environ.get("ETF_LIMIT") # 測試時可只跑前 N 檔
    if limit:
        etfs = etfs[:int(limit)]

    print("準備寫入", len(etfs), "檔被動式 ETF 到 MySQL ...")
    total_p = 0
    total_d = 0
    total_s = 0
    failed = []
    i = 0
    for e in etfs:
        i = i + 1
        stock_id = e["stock_id"]
        market = e["market"]
        try:
            data = fetch_chart(stock_id, market)       # 依市場給 .TW / .TWO
            total_p = total_p + save_prices(parse_prices(stock_id, data))
            total_d = total_d + save_dividends(parse_dividends(stock_id, data))
            total_s = total_s + save_splits(parse_splits(stock_id, data))
        except Exception as err:
            failed.append(stock_id)                    # 單檔失敗不中斷整批
            print("  ⚠", stock_id, "失敗：", str(err)[:60])
        time.sleep(1)                                  # 禮貌：放慢，避免被擋
        if i % 20 == 0:
            print("  進度", i, "/", len(etfs))

    print("完成：股價", total_p, "筆、除權息", total_d, "筆、分割", total_s, "筆 已寫入 MySQL")
    if failed:
        print("失敗", len(failed), "檔：", failed)


main()
