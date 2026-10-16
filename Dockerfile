# 被動式 ETF 抓價入庫 — Docker image（對應課程 12 Docker、13 uv）
# 目標：把「抓被動式 ETF 股價/除權息/分割 → 寫進 MySQL」的程式打包成一個可攜的 image。

FROM python:3.11-slim

# 安裝 uv（Rust 寫的 Python 套件管理工具，course 13）
RUN pip install --no-cache-dir uv

WORKDIR /app

# 先只複製依賴檔，善用 Docker layer 快取：依賴沒變就不用重裝
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

# 再複製程式碼
COPY project/ ./project/

# 連線資訊「預設值」——實際帳密請在執行時用 -e 或 docker-compose 傳入，不要寫死！
ENV MYSQL_HOST=mysql \
    MYSQL_PORT=3306 \
    MYSQL_USER=root \
    MYSQL_DB=etf

# 容器啟動時要執行的指令：抓被動式 ETF → 寫進 MySQL
CMD ["uv", "run", "python", "project/etf_to_mysql.py"]
