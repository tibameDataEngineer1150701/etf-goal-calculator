# ETF 分散式爬蟲 — 主管（producer）
# 讀 stock.etf_list，上市送到 twse queue、上櫃送到 tpex queue。
# 發送任務：  uv run python etf_producer.py

import os
from etf_to_mysql import get_etf_list_from_db
from etf_tasks import crawl_one


def queue_for(market):
    if (market or "").strip().lower() == "tpex":
        return "tpex"
    return "twse"


def main():
    etfs = get_etf_list_from_db()                   # [{stock_id, market}, ...]
    limit = os.environ.get("ETF_LIMIT")
    if limit:
        etfs = etfs[:int(limit)]
    for e in etfs:
        queue = queue_for(e["market"])
        crawl_one.apply_async(args=[e["stock_id"], e["market"]], queue=queue)
    print(f"已發送 {len(etfs)} 個 ETF 爬蟲任務到 RabbitMQ（twse / tpex 分開）")


if __name__ == "__main__":
    main()
