# ETF 分散式爬蟲 — 任務定義（tasks）
# 對應課程 14（@app.task 註冊任務）
# 工人收到 crawl_one(stock_id, market) → 抓 Yahoo → 寫進 MySQL（重用 etf_to_mysql 的函式）

from etf_worker import app
from etf_to_mysql import (fetch_chart, parse_prices, parse_dividends, parse_splits,
                          save_prices, save_dividends, save_splits)


@app.task(name="etf.crawl_one")
def crawl_one(stock_id, market):
    # 一個任務 = 抓一檔 ETF、寫三張表
    data = fetch_chart(stock_id, market)            # 依市場給 .TW / .TWO
    p = save_prices(parse_prices(stock_id, data))
    d = save_dividends(parse_dividends(stock_id, data))
    s = save_splits(parse_splits(stock_id, data))
    return {"stock_id": stock_id, "prices": p, "dividends": d, "splits": s}
