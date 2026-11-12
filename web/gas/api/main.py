"""v4 candidate: authenticated v2 catalogue and single-ETF snapshot. No DB writes."""
import copy
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response

from catalog import MAX_ITEMS, Policy, assess, build_catalog, price_sql, valid_symbol
from snapshot import HOUSING_SQL, SourceError, TAIPEI, build_snapshot

LOG = logging.getLogger("etf_v4")


class Settings:
    def __init__(self):
        self.token = Path(os.environ["API_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
        self.password = Path(os.environ["MYSQL_PASSWORD_FILE"]).read_text(encoding="utf-8").rstrip("\r\n")
        self.host = os.getenv("MYSQL_HOST", "mysql")
        self.user = os.getenv("MYSQL_USER", "etf_web_readonly")
        self.policy = Policy(int(os.getenv("MAX_PRICE_AGE_DAYS", "14")), int(os.getenv("MAX_LIST_AGE_DAYS", "35")))
        if len(self.token) < 32 or not self.password or self.user.lower() == "root":
            raise ValueError("Non-root read-only credentials and a strong API token are required")


class Unavailable(Exception):
    def __init__(self, entry):
        self.entry = entry


class NotFound(Exception):
    pass


def read_source(settings, symbol=None):
    if symbol is not None and not valid_symbol(symbol):
        raise SourceError("Invalid selected ETF identity")
    with closing(pymysql.connect(
        host=settings.host, port=3306, user=settings.user, password=settings.password,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5, read_timeout=15, write_timeout=5, autocommit=False,
    )) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=10000")
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
                cursor.execute(price_sql(symbol is not None), (symbol, symbol) if symbol is not None else None)
                rows = cursor.fetchall()
                now = datetime.now(TAIPEI)
                if symbol is None:
                    return build_catalog(rows, now, settings.policy)
                if not rows:
                    raise NotFound()
                if len(rows) != 1 or rows[0]["stock_id"] != symbol:
                    raise SourceError("Duplicate or mismatched ETF identity")
                entry = assess(rows[0], now, settings.policy)
                if not entry["eligible"]:
                    raise Unavailable(entry)
                cursor.execute(HOUSING_SQL, ("中性",))
                houses = cursor.fetchall()
            snapshot = build_snapshot(rows, houses, now, entry)
            # Eligibility is checked again on snapshot refresh, not trusted from the UI.
            return snapshot
        finally:
            conn.rollback()


class BoundedReader:
    def __init__(self, read, ttl=60, capacity=64):
        self.read, self.ttl, self.capacity = read, ttl, capacity
        self.lock = threading.Lock()
        self.values = OrderedDict()

    def get(self, key):
        with self.lock:
            now = time.monotonic()
            if key in self.values:
                expires, value = self.values[key]
                if now < expires:
                    self.values.move_to_end(key)
                    return copy.deepcopy(value)
                del self.values[key]
            # Refresh failure cannot return an expired cache.
            value = self.read(key)
            self.values[key] = (time.monotonic() + self.ttl, copy.deepcopy(value))
            while len(self.values) > self.capacity:
                self.values.popitem(last=False)
            return value


def create_app(settings=None, catalog_reader=None, snapshot_reader=None):
    settings = settings or Settings()
    catalog_reader = catalog_reader or BoundedReader(lambda _: read_source(settings), capacity=1)
    snapshot_reader = snapshot_reader or BoundedReader(lambda symbol: read_source(settings, symbol))
    app = FastAPI(title="ETF database catalogue v4 candidate", docs_url=None, redoc_url=None, openapi_url=None)
    request_times = deque()
    rate_lock = threading.Lock()
    rate_limit = 120  # Global process cap for the small team-test VM; no per-user identity stored.

    def auth(authorization: str | None = Header(default=None)):
        if authorization is None or not secrets.compare_digest(
            authorization.encode(), ("Bearer " + settings.token).encode()
        ):
            raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})
        with rate_lock:
            now = time.monotonic()
            while request_times and request_times[0] <= now - 60:
                request_times.popleft()
            if len(request_times) >= rate_limit:
                raise HTTPException(429, "Team test rate limit; retry later", headers={"Retry-After": "60", "Cache-Control": "no-store"})
            request_times.append(now)

    def get(reader, key):
        try:
            return reader.get(key)
        except NotFound:
            raise HTTPException(404, {"code": "ETF_NOT_FOUND", "message": "ETF 不在資料庫清單中"}) from None
        except Unavailable as exc:
            raise HTTPException(422, {"code": "ETF_UNAVAILABLE", "message": exc.entry["reasonText"], "reasons": exc.entry["reasons"]}) from None
        except Exception:
            LOG.warning("source_unavailable_or_invalid")
            raise HTTPException(503, {"code": "SOURCE_UNAVAILABLE", "message": "來源無法讀取或資料不完整；未使用替代資料"}) from None

    def secure(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"

    @app.get("/health/live")
    def live():
        return {"status": "ok", "service": "etf-live-data", "version": "4.0-candidate"}

    @app.get("/v2/etfs", dependencies=[Depends(auth)])
    def catalogue(response: Response, offset: int = Query(0, ge=0, le=MAX_ITEMS),
                  limit: int = Query(100, ge=1, le=100), catalog_id: str | None = None):
        data = get(catalog_reader, "catalog")
        if catalog_id is not None and catalog_id != data["catalogId"]:
            raise HTTPException(409, {"code": "CATALOG_CHANGED", "message": "清單已更新，請重新載入"})
        secure(response)
        page = {k: v for k, v in data.items() if k != "items"}
        page.update(items=data["items"][offset:offset + limit], offset=offset,
                    nextOffset=offset + limit if offset + limit < data["total"] else None)
        return {"mode": "LIVE", "catalog": page, "apiCacheMaxAgeSeconds": catalog_reader.ttl}

    @app.get("/v2/snapshot", dependencies=[Depends(auth)])
    def selected_snapshot(response: Response, symbol: str):
        if not valid_symbol(symbol):
            raise HTTPException(400, {"code": "INVALID_SYMBOL", "message": "ETF 代號格式無效"})
        data = get(snapshot_reader, symbol)
        secure(response)
        return {"mode": "LIVE", "snapshot": data, "apiCacheMaxAgeSeconds": snapshot_reader.ttl}

    return app
