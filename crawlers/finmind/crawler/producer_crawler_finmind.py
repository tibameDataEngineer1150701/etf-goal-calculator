# # Producer: 負責「派送任務」, 把工作丟到 RabbitMQ 給 worker 處理
# # 對應的 consumer 就是 tasks_crawler_finmind.py 裡註冊的 crawler_finmind task
# #from crawler.tasks_crawler_finmind import crawler_finmind


# from crawler.tasks_crawler_finmind import crawler_finmind_print

# # for 迴圈, 可一次發送多個任務
# # 這樣一次就能派送 5 支股票的爬蟲任務到 RabbitMQ
# # Celery worker 會從 RabbitMQ 取出任務並平行處理, 比循序執行快很多
# #for stock_id in ["2330", "0050", "2317", "0056", "00713"]:
# for stock_id in ["0050"]:
#     print(stock_id)
#     # .delay() 是 Celery 的非同步派送捷徑, 呼叫完會立刻回傳, 不等 task 執行完
# #crawler_finmind.delay(stock_id=stock_id)
# crawler_finmind_print.delay(stock_id=stock_id)

import requests
#from crawler.tasks_crawler_finmind import crawler_finmind_print
from crawler.tasks_crawler_finmind import crawler_finmind

url = "https://api.finmindtrade.com/api/v4/data"

parameter = {
    "dataset": "TaiwanStockInfo"
}

resp = requests.get(url, params=parameter)
data = resp.json()

stock_ids = [row["stock_id"] for row in data["data"]]

# #去除重複的股票代碼，並排序
# stock_ids = sorted(set(stock_ids)) 
# print(stock_ids[:10])
# print(len(stock_ids))

# #for stock_id in ["2330", "0050", "2317", "0056", "00713"]:
# for stock_id in stock_ids[:3]:
#     print(stock_id)
#     crawler_finmind_print.delay(stock_id=stock_id)
#     # .delay() 是 Celery 的非同步派送捷徑, 呼叫完會立刻回傳, 不等 task 執行完



stock_ids = ["0050"]

for stock_id in stock_ids:
    print(stock_id)
    crawler_finmind.delay(stock_id=stock_id)