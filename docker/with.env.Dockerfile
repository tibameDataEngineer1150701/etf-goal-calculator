# build 時用 DEV 以外的 DOCKER 區段產生 .env。帳密來自 local.ini，不寫在這個檔案裡。
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY crawlers/etf/pyproject.toml crawlers/etf/uv.lock crawlers/etf/.python-version ./
RUN uv sync --frozen

COPY crawlers/etf/etf_to_mysql.py crawlers/etf/etf_universe.py \
     crawlers/etf/etf_worker.py crawlers/etf/etf_tasks.py \
     crawlers/etf/etf_producer.py crawlers/etf/etf_scheduler.py \
     crawlers/etf/genenv.py crawlers/etf/local.ini.example ./
RUN cp local.ini.example local.ini && ENV=DOCKER python genenv.py

CMD ["uv", "run", "python", "etf_producer.py"]
