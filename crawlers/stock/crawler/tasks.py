import os

from celery.utils.log import get_task_logger

from crawler.finmind_etf_list import build_etf_list
from crawler.save_etf_list import save_etf_list
from crawler.worker import app

logger = get_task_logger(__name__)


@app.task(name="crawler.tasks.crawl_etf_list")
def crawl_etf_list():
    password = os.environ.get("MYSQL_PASSWORD")
    if not password:
        raise RuntimeError("請使用 python -m crawler.run_worker 啟動 worker")

    etfs, summary = build_etf_list()
    for label, count in summary.items():
        logger.info("%s：%s", label, count)

    saved_count = save_etf_list(etfs, password)
    logger.info("MySQL 入庫完成：本次提交 %s 筆 ETF", saved_count)

    return {
        "summary": summary,
        "submitted_count": saved_count,
    }