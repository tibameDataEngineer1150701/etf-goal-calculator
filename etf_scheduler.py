# 簡易版定時更新（apscheduler）— 對應課程 21
# 若還沒把 Airflow/Swarm 架好，可先用這支達成作業要求「專題 MySQL 資料自動定期更新」。
# 需要套件： uv add apscheduler loguru
# 用法：
#   export MYSQL_HOST=... MYSQL_USER=... MYSQL_PASSWORD=... MYSQL_DB=etf ETF_LIST_DB=stock
#   uv run python etf_scheduler.py        # 會持續執行，依排程定時更新

import etf_to_mysql                       # 匯入主程式（有 if __name__ 保護，不會自動執行）
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger


def job():
    logger.info("開始定時抓取 ETF，更新 MySQL ...")
    try:
        etf_to_mysql.main()               # 讀 stock.etf_list → 抓價 → 寫 etf_price
        logger.info("ETF 更新完成")
    except Exception as err:
        logger.error(f"ETF 更新失敗：{err}")


scheduler = BlockingScheduler(timezone="Asia/Taipei")
# 週一~週五 15:00（台股收盤後）各跑一次
scheduler.add_job(job, "cron", day_of_week="mon-fri", hour=15, minute=0)

if __name__ == "__main__":
    logger.info("排程已啟動：週一~週五 15:00 自動更新 ETF 資料。按 Ctrl+C 結束。")
    scheduler.start()                     # Blocking 模式會持續運作，不用額外 while+sleep
