# ETF 分散式爬蟲 — 主管（producer）
# 對應課程 14（producer 發送任務）
# 讀組員 的 stock.etf_list，一檔 ETF 發一個任務到 RabbitMQ，由多個工人平行處理。
# 發送任務：  uv run python etf_producer.py

from etf_to_mysql import get_etf_list_from_db
from etf_tasks import crawl_one


def main():
    etfs = get_etf_list_from_db()                   # [{stock_id, market}, ...]
    for e in etfs:
        crawl_one.delay(e["stock_id"], e["market"]) # .delay() = 把任務送進 RabbitMQ 排隊
    print(f"已發送 {len(etfs)} 個 ETF 爬蟲任務到 RabbitMQ（由工人平行處理、寫入 MySQL）")


if __name__ == "__main__":
    main()
