"""啟動前輸入 MySQL 密碼，再啟動 Celery worker。"""

import os
from getpass import getpass


def main():
    password = getpass("請輸入本機 MySQL user 密碼：")
    if not password:
        raise SystemExit("未輸入密碼，取消啟動")

    # 僅放在本次程序環境，不寫入原始碼或設定檔
    os.environ["MYSQL_PASSWORD"] = password
    os.environ["RABBITMQ_HOST"] = "127.0.0.1"

    from crawler.worker import app

    try:
        app.worker_main([
            "worker",
            "--queues=etf_list",
            "--loglevel=info",
            "--concurrency=1",
            "--hostname=etf_practice@%h",
        ])
    finally:
        os.environ.pop("MYSQL_PASSWORD", None)


if __name__ == "__main__":
    main()