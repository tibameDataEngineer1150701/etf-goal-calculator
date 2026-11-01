# 簡易版定時更新（apscheduler）
# 若還沒把 Airflow / Swarm 架好，可先用這支讓 MySQL 的 ETF 資料定時更新。
# 需要套件： uv add apscheduler loguru
# 用法：
#   export MYSQL_HOST=... MYSQL_USER=... MYSQL_PASSWORD=... MYSQL_DB=etf ETF_LIST_DB=stock
#   uv run python etf_scheduler.py        # 會持續執行，依排程定時更新

import etf_producer
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger


def job():
    logger.info("開始派送 ETF 任務到 RabbitMQ ...")
    try:
        etf_producer.main()               # 讀 stock.etf_list → 送到 twse / tpex queue
        logger.info("ETF 任務已派送")
    except Exception as err:
        logger.error(f"ETF 派送失敗：{err}")


scheduler = BlockingScheduler(timezone="Asia/Taipei")
# 週一~週五 15:00（台股收盤後）各跑一次
scheduler.add_job(job, "cron", day_of_week="mon-fri", hour=15, minute=0)

if __name__ == "__main__":
    logger.info("排程已啟動：週一~週五 15:00 自動更新 ETF 資料。按 Ctrl+C 結束。")
    scheduler.start()                     # Blocking 模式會持續運作，不用額外 while+sleep
