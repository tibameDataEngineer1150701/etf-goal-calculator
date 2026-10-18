FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.11-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser crawler/ ./crawler/

USER appuser

CMD ["python", "-m", "celery", "-A", "crawler.worker", "worker", "--queues=etf_list", "--loglevel=info", "--concurrency=1", "--hostname=etf_docker@%h"]