"""以 APScheduler 定時派送 ETF 爬蟲任務。"""

import logging
import os
import signal

from apscheduler.schedulers.blocking import BlockingScheduler

from crawler.tasks import crawl_etf_list

logger = logging.getLogger(__name__)


def dispatch_etf_task():
    result = crawl_etf_list.delay()
    logger.info("已派送 ETF 任務，ID：%s", result.id)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    seconds = int(os.environ.get("SCHEDULE_SECONDS", "43200"))
    if seconds < 60:
        raise ValueError("排程間隔至少 60 秒")

    scheduler = BlockingScheduler(timezone="Asia/Taipei")
    scheduler.add_job(
        dispatch_etf_task,
        trigger="interval",
        seconds=seconds,
        id="dispatch_etf_list",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    def stop_scheduler(signum, frame):
        if scheduler.running:
            scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, stop_scheduler)
    logger.info("ETF 排程啟動，間隔 %s 秒", seconds)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()