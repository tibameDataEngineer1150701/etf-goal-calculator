from crawler.tasks import crawl_etf_list


if __name__ == "__main__":
    result = crawl_etf_list.delay()
    print("已送出 ETF 爬蟲任務，任務 ID：", result.id)