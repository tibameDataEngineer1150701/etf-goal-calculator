"""從 FinMind 取得 ETF 清單，依明確規則排除不符合的標的。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import requests


def fetch_data(dataset):
    """取得指定的 FinMind 資料集；失敗時停止，不回傳假空清單。"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": dataset}

    # 發送請求，並檢查 HTTP 是否成功
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    # 檢查 FinMind 回應本身是否成功
    if not isinstance(payload, dict):
        raise ValueError(f"{dataset} 回應格式不是字典")
    if payload.get("status") != 200:
        raise ValueError(f"{dataset} 回應失敗：{payload.get('msg')}")

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{dataset} 格式不符或沒有資料")

    return rows


def build_etf_list():
    """取得三份資料，回傳篩選清單與各階段統計。"""
    stock_rows = fetch_data("TaiwanStockInfo")
    active_rows = fetch_data("TaiwanStockActiveETFInfo")
    delisted_rows = fetch_data("TaiwanStockDelisting")

    # 同一代碼保留日期最新的一筆資料
    latest = {}
    for row in stock_rows:
        stock_id = row["stock_id"].strip().upper()
        previous = latest.get(stock_id)
        if previous is None or row["date"] > previous["date"]:
            latest[stock_id] = dict(row, stock_id=stock_id)

    # 收集上市、上櫃且分類包含 ETF 的候選
    candidates = []
    for row in latest.values():
        category = row.get("industry_category", "")
        market = row.get("type", "")
        if "ETF" in category and market in ("twse", "tpex"):
            candidates.append(row)

    # 主動式 ETF 的代碼集合
    active_ids = {
        row["stock_id"].strip().upper()
        for row in active_rows
    }

    # 收集截至台灣今天，已生效的下市櫃代碼
    today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    delisted_ids = {
        row["stock_id"].strip().upper()
        for row in delisted_rows
        if row["date"] <= today
    }

    selected_etfs = []
    excluded_active = []
    excluded_leveraged_inverse = []
    excluded_delisted = []

    # 依序篩選，每筆只計入第一個符合的排除原因
    for row in candidates:
        stock_id = row["stock_id"]

        # 第一關：排除 FinMind 主動式 ETF 清單中的代碼
        if stock_id in active_ids:
            excluded_active.append(row)
            continue

        # 第二關：排除槓桿與反向，包括外幣版本
        # Python 從 0 起算，第六碼的位置是 [5]
        if len(stock_id) == 6 and stock_id[5] in ("L", "M", "R", "S"):
            excluded_leveraged_inverse.append(row)
            continue

        # 第三關：排除已生效的下市櫃代碼
        # 不用 TaiwanStockInfo 的更新日期推測是否重新掛牌
        if stock_id in delisted_ids:
            excluded_delisted.append(row)
            continue

        # 三關都通過，加入結果
        selected_etfs.append(row)

    # 依代碼排序，方便每次執行後比較
    selected_etfs.sort(key=lambda row: row["stock_id"])

    summary = {
        "台股總覽原始筆數": len(stock_rows),
        "ETF 候選筆數": len(candidates),
        "排除主動式筆數": len(excluded_active),
        "排除槓桿／反向筆數": len(excluded_leveraged_inverse),
        "排除下市櫃筆數": len(excluded_delisted),
        "依目前規則保留筆數": len(selected_etfs),
    }

    # 核對每筆候選都有被分類，避免漏算
    classified_count = (
        len(selected_etfs)
        + len(excluded_active)
        + len(excluded_leveraged_inverse)
        + len(excluded_delisted)
    )
    if classified_count != len(candidates):
        raise ValueError("篩選前後筆數不一致")

    if not selected_etfs:
        raise ValueError("篩選結果為空，請檢查來源與規則")

    return selected_etfs, summary


# 直接執行此檔案時，才抓資料並印出結果
# 之後其他模組可以匯入 build_etf_list，不會自動執行下面這段
if __name__ == "__main__":
    etfs, summary = build_etf_list()

    for label, count in summary.items():
        print(f"{label}：{count}")

    print("\n保留清單前五筆：")
    for row in etfs[:5]:
        print(row)