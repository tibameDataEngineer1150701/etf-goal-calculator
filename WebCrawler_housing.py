# Real Estate Web Crawler, Taiwan Real Estate Transaction Data Engineering & Analytics Pipeline
# 內政部不動產交易實價查詢服務網 -> 資料下載及申請 -> 不動產成交案件實際資訊資料供應系統 -> 登入https://plvr.land.moi.gov.tw/Index
# 網站不是直接下載一個 ZIP，而是在瀏覽器中先建立 ZIP，再觸發下載。負責把檔案放進 ZIP 的那一段，通常是真正的資料來源或 AJAX 請求
# 觀察下載的每季資料網址

# loadAjaxUrl() 和 clickIndex() 不是用剛才搜尋的這幾種函式宣告形式直接寫在 DownloadOpenData HTML 裡，可能藏在某個外部 JS
# 最有效率的方法:直接讓瀏覽器告訴我們它實際送了什麼 Request，也就是看 Chrome DevTools → Network

# Download_ajax_active 只負責載入下載頁面；downloadManager.js 負責在瀏覽器內組合 ZIP。真正的資料取得邏輯應該在其他 JavaScript 檔案或該頁面的內嵌程式碼中

import requests
import os
import zipfile

"""夢市集軟體技術有限公司https://mosji.co/doc/python-topic-house-price-analysis
def actual_price_crawler(year, season):
    print(f'開始下載{year}年第{season}季實價登錄資料 ..... ', end='')
    url = f'https://plvr.land.moi.gov.tw//DownloadSeason?season={year}S{season}&type=zip&fileName=lvr_landcsv.zip'

    # 下載實價登錄OpenData
    response = requests.get(url)

    # 將下載的檔案寫入本地
    filename = f'lvr_landcsv-{year}S{season}'
    with open(f'{filename}.zip', 'wb') as f:
        f.write(response.content)

    # 以檔案名稱建立解壓縮目錄
    if not os.path.isdir(filename):
        os.mkdir(filename)

    # 解壓縮zip檔案
    with zipfile.ZipFile(f'{filename}.zip', 'r') as zip_ref:
        zip_ref.extractall(filename)

    print('完成.')


只要如下呼叫就可以直接將114年第一季的實價登錄檔案下載到本地端並自動解壓縮：
actual_price_crawler(114, 1)

如果你想從民國110年第一季下載到現在的所有實價登錄資料，只要使用for迴圈就可以了，例如：

for year in range(105, 116):
    for season in range(1, 5):
        actual_price_crawler(year, season)

最後一季

actual_price_crawler(114, 1)

解壓縮後的檔案非常多，裡面有一個檔案：manifest.csv，這個檔案裡面的內容就是說明每個檔案的資料

跟房屋交易相關的檔案大概有三種：檔名第一個問號為根據地區會使用不用的英文字母表示。

?_lvr_land_a：不動產買賣
?_lvr_land_b：預售屋買賣
?_lvr_land_c：不動產租賃

"""


import requests
import zipfile
from pathlib import Path
import io
import time

BASE_URL = "https://plvr.land.moi.gov.tw/DownloadSeason"

# 先試著下載「一季」資料
def download_season(roc_year, quarter, output_dir="C:/Users/user/PycharmProjects"):
    """
    下載指定民國年份、季度的實價登錄 OpenData ZIP。

    例如：
    download_season(105, 1)
    → 105S1
    """

    season = f"{roc_year}S{quarter}"

    # 比js_urls(未登入)更乾淨的資料取得 API/endpoint (評估網頁運作邏輯，使用者須登入，才更容易下載)
    url = (
        f"{BASE_URL}"
        f"?season={season}"
        f"&type=zip"
        f"&fileName=lvr_landcsv.zip"
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / f"{season}_lvr_landcsv.zip"

    print("=" * 70)  # 分隔線
    print(f"開始下載：{season}")
    print(url)  # 回傳該zip的下載連結

    # 已經下載過就跳過，避免每次執行會重複下載zip(for incremental pipeline)
    if zip_path.exists():
        print(f"⚠️ 已存在，跳過下載：{zip_path}")
        return zip_path

    try:
        response = requests.get(
            url,
            timeout=120,
            verify=False
        )

        print("HTTP Status:", response.status_code)
        print("Content-Type:", response.headers.get("Content-Type"))
        print("Size:", len(response.content), "bytes")

        response.raise_for_status()

        # 確認是不是 ZIP
        if not zipfile.is_zipfile(io.BytesIO(response.content)):
            print("❌ 下載結果不是有效 ZIP")
            print(response.text[:500])
            return None

        # 儲存 ZIP
        with open(zip_path, "wb") as f:
            f.write(response.content)

        print(f"✅ ZIP 已儲存：{zip_path}")

        return zip_path

    except requests.RequestException as e:
        print(f"❌ 下載失敗：{e}")
        return None

zip_path = download_season(105, 1)


# unzip and extract data from downloaded zips - try 105S1 first
def extract_season(zip_path, extract_dir="C:/Users/user/PycharmProjects"):
    """
    將指定季度 ZIP 解壓縮
    """

    zip_path = Path(zip_path)

    season = zip_path.name.split("_")[0]

    extract_dir = Path(extract_dir) / season
    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"開始解壓縮：{season}")

    # 如果已解壓縮，則跳過
    if any(extract_dir.iterdir()):
        print(f"⚠️ 已存在解壓縮資料，跳過：{extract_dir}")
        return extract_dir

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    print(f"✅ 解壓縮完成：{extract_dir}")

    return extract_dir


if zip_path:
    extract_path = extract_season(zip_path)


# # 寫一個可重複使用的 function，每月/每期資料更新後，可以重新執行 pipeline，無須改 code
# # 自動取得目前日期
# from datetime import datetime
#
#
# def current_roc_year():
#     return datetime.now().year - 1911  # 換算成民國年，配合網站連結的寫法
#
#
# def current_quarter():
#     month = datetime.now().month
#     return (month - 1) // 3 + 1
#
#
# print(current_roc_year())  # end_year = current_roc_year
# print(current_quarter())  # end_quarter = current_quarter
#


"""
## data pipeline ##
def run_pipeline(start_year=105):

    end_year = current_roc_year()
    end_quarter = current_quarter()

    for year in range(start_year, end_year + 1):

        for quarter in range(1, 5):

            # 不要下載未來季度
            if year == end_year and quarter > end_quarter:
                break

            print(f"\nProcessing {year}S{quarter}")

            zip_path = download_season(
                year,
                quarter,
                output_dir="data/raw"
            )

            if zip_path:
                extract_season(
                    zip_path,
                    extract_dir="data/extracted"
                )

            time.sleep(1)
"""

# 解壓縮後，自動掃描所有 CSV，依照檔名中的 _lvr_land_a / b / c 判斷資料內容
# 每個 ZIP 裡有6份schema, 1份manifest, 檔案名稱首字母是地區代碼, _lvr_land_a, _lvr_land_b, _lvr_land_c 是真正需辨識的資料
# 自動辨識 manifest.csv + a / b / c
from pathlib import Path


def identify_files(extract_dir):
    """
    自動辨識解壓縮後的：
    1. manifest.csv
    2. 不動產買賣 (_lvr_land_a)
    3. 預售屋買賣 (_lvr_land_b)
    4. 不動產租賃 (_lvr_land_c)
    """

    extract_dir = Path(extract_dir)

    result = {
        "manifest": None,
        "schema": [],
        "land_a": [],
        "land_b": [],
        "land_c": []
    }

    # 掃描所有 CSV
    csv_files = list(extract_dir.rglob("*.csv"))

    for file in csv_files:

        filename = file.name.lower()

        # manifest
        if filename == "manifest.csv":
            result["manifest"] = file

        # schema
        elif "schema" in filename:
            result["schema"].append(file)

        # 不動產買賣
        elif "_lvr_land_a" in filename:
            result["land_a"].append(file)

        # 預售屋買賣
        elif "_lvr_land_b" in filename:
            result["land_b"].append(file)

        # 不動產租賃
        elif "_lvr_land_c" in filename:
            result["land_c"].append(file)

    return result

files = identify_files(extract_path)

print("Manifest:")
print(files["manifest"])

print("\nSchema:")
for file in files["schema"]:
    print(file)

print("\n不動產買賣 A:")
for file in files["land_a"]:
    print(file)

print("\n預售屋買賣 B:")
for file in files["land_b"]:
    print(file)

print("\n不動產租賃 C:")
for file in files["land_c"]:
    print(file)

print("\n========== 檔案統計 ==========")

print("Manifest:", 1 if files["manifest"] else 0)
print("Schema:", len(files["schema"]) if files["schema"] else 0)
print("不動產買賣(a):", len(files["land_a"]), "份")
print("預售屋買賣(b):", len(files["land_b"]), "份")
print("不動產租賃(c):", len(files["land_c"]), "份")



