# 全台股標的 → 篩選 ETF → 篩選被動式（產生「收錄清單」）
# 資料來源：FinMind TaiwanStockInfo（回傳 JSON，含每檔的分類 industry_category）
# 對應課程：05(API+JSON)、07(pandas)
# 用法： uv run python project/etf_universe.py   → 產生 passive_etf_list.csv
#
# 篩選規則（被動式 = 追蹤指數的原型 ETF）：
#   排除 槓桿型(代號結尾 L)、反向型(結尾 R)、主動式(結尾 A 或名稱含「主動」)
#   以及名稱含 正2 / 反1 / 槓桿 / 反向 等字樣。
#   註：這是依台股命名慣例的「近似判斷」，商品期貨(結尾 U)、債券(結尾 B) 仍算被動式；
#       若報告只想要股票/債券型，可自行再排除 U。

import json
import urllib.request
import pandas as pd

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_all_stocks():
    # 抓「全台股基本資料」，回傳一個 list（每筆是一檔的 dict）
    request = urllib.request.Request(FINMIND_URL, headers=HEADERS)
    response = urllib.request.urlopen(request, timeout=40)
    data = json.loads(response.read())
    return data["data"]


def is_etf(category):
    # FinMind 把 ETF 的分類標成含 "ETF" 或 "指數股票型"
    if category is None:
        return False
    return ("ETF" in category) or ("指數股票型" in category)


def is_passive(stock_id, stock_name):
    if stock_name is None:
        stock_name = ""
    last = stock_id[-1:]                  # 代號最後一個字
    if last == "L" or last == "R":        # L=槓桿型、R=反向型 → 不是被動原型
        return False
    if last == "A":                        # A=主動式 ETF
        return False
    for word in ["正2", "反1", "槓桿", "反向", "2X", "單日", "主動"]:
        if word in stock_name:
            return False
    return True


def get_passive_etf_list():
    rows = fetch_all_stocks()

    # 先挑出所有 ETF，用 dict 去重（同一檔可能出現多列）
    etf_info = {}
    for r in rows:
        stock_id = r.get("stock_id", "")
        category = r.get("industry_category", "")
        if is_etf(category):
            etf_info[stock_id] = (r.get("stock_name", ""), r.get("type", ""))  # type: twse/tpex

    # 再從 ETF 裡挑出被動式
    result = []
    for stock_id in etf_info:
        name, market = etf_info[stock_id]
        if is_passive(stock_id, name):
            result.append({"stock_id": stock_id, "stock_name": name, "market": market})

    result.sort(key=lambda x: x["stock_id"])   # 依代號排序
    return result


def main():
    etfs = get_passive_etf_list()
    df = pd.DataFrame(etfs)
    df.to_csv("passive_etf_list.csv", index=False, encoding="utf-8")
    print("被動式 ETF 共", len(df), "檔，已存成 passive_etf_list.csv")
    print(df.head(10).to_string(index=False))


# 只有「直接執行這個檔」時才產生 CSV；被別的程式 import 時不會自動跑
if __name__ == "__main__":
    main()
