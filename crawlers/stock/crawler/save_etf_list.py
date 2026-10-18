"""將篩選後的 ETF 清單寫入 MySQL。"""

import os
from datetime import date, datetime
from getpass import getpass
from zoneinfo import ZoneInfo

import pymysql

from crawler.finmind_etf_list import build_etf_list


def save_etf_list(etfs, password):
    if not etfs:
        raise ValueError("ETF 清單為空，停止入庫")
    if not password:
        raise ValueError("未提供 MySQL 密碼")

    seen_at = datetime.now(ZoneInfo("Asia/Taipei")).replace(tzinfo=None)
    records = []
    seen_ids = set()

    for row in etfs:
        stock_id = row["stock_id"]
        if stock_id in seen_ids:
            raise ValueError(f"ETF 代碼重複：{stock_id}")
        seen_ids.add(stock_id)

        name = row["stock_name"]
        category = row["industry_category"]
        market = row["type"]
        source_date = date.fromisoformat(row["date"])
        records.append((
            stock_id, name, category, market, source_date, seen_at,
            name, category, market, source_date, seen_at,
        ))

    sql = """
        INSERT INTO etf_list (
            stock_id, stock_name, industry_category,
            market, source_date, last_seen_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name = %s,
            industry_category = %s,
            market = %s,
            source_date = %s,
            last_seen_at = %s
    """

    connection = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3307")),
        user=os.environ.get("MYSQL_USER", "user"),
        password=password,
        database=os.environ.get("MYSQL_DATABASE", "stock"),
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )

    try:
        with connection.cursor() as cursor:
            for record in records:
                cursor.execute(sql, record)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return len(records)


if __name__ == "__main__":
    password = getpass("請輸入 MySQL user 密碼：")
    etfs, summary = build_etf_list()
    for label, count in summary.items():
        print(f"{label}：{count}")

    saved_count = save_etf_list(etfs, password)
    print(f"本次已提交 {saved_count} 筆 ETF 至 MySQL")