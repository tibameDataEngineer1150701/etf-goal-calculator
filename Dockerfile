# 被動式 ETF 抓價入庫 — Docker image（對應課程 12 Docker、13 uv）
# 注意：本 repo 檔案放在根目錄（扁平結構），故不使用 project/ 子資料夾。

FROM python:3.11-slim

# 安裝 uv（Python 套件管理工具，course 13）
RUN pip install --no-cache-dir uv

WORKDIR /app

# 先複製依賴檔，善用 layer 快取
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

# 複製程式（根目錄的所有 .py 與 schema.sql）
COPY *.py schema.sql ./

# 連線資訊「預設值」——實際帳密請用 -e 或 compose 傳入，不要寫死！
ENV MYSQL_HOST=mysql \
    MYSQL_PORT=3306 \
    MYSQL_USER=root \
    MYSQL_DB=etf

# 容器啟動時：抓被動式 ETF → 寫進 MySQL
CMD ["uv", "run", "python", "etf_to_mysql.py"]
