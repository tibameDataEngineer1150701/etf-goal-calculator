# 被動式 ETF 資料收集
# 用法： uv run python project/etf_fetch.py

import json
import time
import datetime
import urllib.request
import pandas as pd


# ── 設定（哪幾檔ETF、過去幾年）──
STOCK_IDS = ["0050", "0056", "006208"]    # 純代號（用字串，前面的 0 才不會不見）
MARKET_SUFFIX = ".TW"                     # 上市 .TW；上櫃 .TWO
YEARS = 10                                # 抓幾年
HEADERS = {"User-Agent": "Mozilla/5.0"}   # 假裝成瀏覽器，避免被擋


def get_date_text(unix_seconds):
    # 把 API 給的「Unix 秒數」轉成 '2026-09-17' 這種文字
    d = datetime.datetime.fromtimestamp(unix_seconds, datetime.timezone.utc)
    return d.strftime("%Y-%m-%d")


def fetch_chart(stock_id):
    # 組出網址，去 Yahoo 抓資料，回傳解析後的 JSON（dict）
    symbol = stock_id + MARKET_SUFFIX          # 0050 + .TW = 0050.TW
    period2 = int(time.time())                 # 現在（秒）
    period1 = period2 - 60 * 60 * 24 * 365 * YEARS   # N 年前（秒）
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={period1}&period2={period2}&interval=1d&events=div,split"

    request = urllib.request.Request(url, headers=HEADERS)
    response = urllib.request.urlopen(request, timeout=30)
    content = response.read()                  # 抓回來的 JSON 文字
    data = json.loads(content)                 # 文字 → Python 的 dict
    return data


def parse_prices(stock_id, data):
    # 把每天的還原收盤挖出來，做成表格：date, stock_id, adj_close
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]                             # 一串日期
    adj_close_list = result["indicators"]["adjclose"][0]["adjclose"]  # 一串還原收盤

    rows = []
    for i in range(len(timestamps)):
        price = adj_close_list[i]
        if price is None:          # 非交易日 → 沒有價格 → 跳過
            continue
        row = {
            "date": get_date_text(timestamps[i]),
            "stock_id": stock_id,
            "adj_close": price,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def parse_dividends(stock_id, data):
    # 把除權息找出來：stock_id, ex_date, amount
    result = data["chart"]["result"][0]
    rows = []
    if "events" in result and "dividends" in result["events"]:
        dividends = result["events"]["dividends"]
        for key in dividends:
            item = dividends[key]
            row = {
                "stock_id": stock_id,
                "ex_date": get_date_text(item["date"]),
                "amount": item["amount"],
            }
            rows.append(row)
    return pd.DataFrame(rows)


def parse_splits(stock_id, data):
    # 把分割找出來（台股 ETF 常常已還原，可能沒有數據）
    result = data["chart"]["result"][0]
    rows = []
    if "events" in result and "splits" in result["events"]:
        splits = result["events"]["splits"]
        for key in splits:
            item = splits[key]
            row = {
                "stock_id": stock_id,
                "split_date": get_date_text(item["date"]),
                "numerator": item["numerator"],
                "denominator": item["denominator"],
                "ratio": item["splitRatio"],
            }
            rows.append(row)
    return pd.DataFrame(rows)


def calc_cagr(prices, stock_id):
    # 用還原收盤算「含息年化報酬」
    one = prices[prices["stock_id"] == stock_id]     # 只留這一檔
    one = one.sort_values("date")                    # 按日期排好
    if len(one) < 2:
        return None
    start_price = one["adj_close"].iloc[0]           # 第一天
    end_price = one["adj_close"].iloc[-1]            # 最後一天
    first_date = pd.to_datetime(one["date"].iloc[0])
    last_date = pd.to_datetime(one["date"].iloc[-1])
    years = (last_date - first_date).days / 365
    cagr = (end_price / start_price) ** (1 / years) - 1
    return cagr


def ask_stock_ids():
    # 讓使用者輸入要查的 ETF；直接按 Enter 就用上面的預設 STOCK_IDS
    text = input("請輸入 ETF 代號（多檔用逗號或空白分隔，直接按 Enter 預設0050, 0056, 006208）：").strip()
    if text == "":
        return STOCK_IDS
    text = text.replace(",", " ")     # 逗號換成空白，這樣兩種分隔都能用
    ids = []
    for x in text.split():            # 依空白切成一個一個代號
        x = x.strip().upper()         # 去掉前後空白，字母轉大寫（如 00679b → 00679B）
        if x != "":
            ids.append(x)
    return ids


def main():
    stock_ids = ask_stock_ids()
    print("這次要抓：", stock_ids)

    all_prices = []
    all_dividends = []
    all_splits = []

    for stock_id in stock_ids:
        print("抓取", stock_id, "...")
        data = fetch_chart(stock_id)
        all_prices.append(parse_prices(stock_id, data))
        all_dividends.append(parse_dividends(stock_id, data))
        all_splits.append(parse_splits(stock_id, data))
        time.sleep(1)               # 每檔之間休息 1 秒（禮貌，避免被擋）

    # 多檔的小表上下疊成一張大表
    prices = pd.concat(all_prices, ignore_index=True)
    dividends = pd.concat(all_dividends, ignore_index=True)
    splits = pd.concat(all_splits, ignore_index=True)

    # 存成 CSV
    prices.to_csv("etf_price.csv", index=False, encoding="utf-8")
    dividends.to_csv("etf_dividend.csv", index=False, encoding="utf-8")
    splits.to_csv("etf_split.csv", index=False, encoding="utf-8")

    print("完成：股價", len(prices), "筆，除權息", len(dividends), "筆，分割", len(splits), "筆")
    print("各 ETF 含息年化報酬：")
    for stock_id in stock_ids:
        cagr = calc_cagr(prices, stock_id)
        if cagr is not None:
            print("  ", stock_id, ":", round(cagr * 100, 2), "% /年")


main()
