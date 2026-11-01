# build 時用 PRODUCTION 區段產生 .env。正式密碼請先改 local.ini，不要提交。
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY crawlers/etf/pyproject.toml crawlers/etf/uv.lock crawlers/etf/.python-version ./
RUN uv sync --frozen

COPY crawlers/etf/etf_to_mysql.py crawlers/etf/etf_universe.py \
     crawlers/etf/etf_worker.py crawlers/etf/etf_tasks.py \
     crawlers/etf/etf_producer.py crawlers/etf/etf_scheduler.py \
     crawlers/etf/genenv.py crawlers/etf/local.ini.example ./
RUN cp local.ini.example local.ini && ENV=PRODUCTION python genenv.py

CMD ["uv", "run", "python", "etf_producer.py"]
