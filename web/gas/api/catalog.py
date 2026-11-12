"""Bounded database-derived catalogue; per-symbol failures are explicit, not fallback data."""
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from snapshot import SourceError, TAIPEI, source_date

MAX_ITEMS = 2000
SYMBOL_PATTERN = r"[0-9][A-Z0-9]{3,19}"
REASONS = {
    "INVALID_METADATA": "清單名稱、代號或市場資料無效",
    "INVALID_LIST_DATE": "清單批次日期無效",
    "NOT_LATEST_LIST_BATCH": "不在最近一次清單寫入批次，資格待確認",
    "STALE_LIST": "清單太久未更新，資格待確認",
    "NO_PRICES": "尚無價格資料",
    "INVALID_PRICES": "價格或日期資料無效",
    "INSUFFICIENT_HISTORY": "未滿 365 天或 240 筆價格",
    "STALE_PRICES": "最新價格已超過允許天數",
}


@dataclass(frozen=True)
class Policy:
    # Local candidate policy, not a claim about the team's current schedule.
    max_price_age_days: int = 14
    max_list_age_days: int = 35
    min_history_days: int = 365
    min_observations: int = 240

    def __post_init__(self):
        for value in asdict(self).values():
            if type(value) is not int or value <= 0:
                raise ValueError("Policy limits must be positive integers")


def valid_symbol(symbol):
    return isinstance(symbol, str) and re.fullmatch(SYMBOL_PATTERN, symbol) is not None


def batch_date(value, now):
    # Legacy DATETIME is written in Asia/Taipei by the list crawler.
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("Missing list batch date")
    if value.tzinfo is None:
        value = value.replace(tzinfo=TAIPEI)
    value = value.astimezone(TAIPEI)
    if value > now.astimezone(TAIPEI):
        raise ValueError("Future list batch date")
    return value


def finite_positive(value):
    return not isinstance(value, bool) and value is not None and math.isfinite(float(value)) and float(value) > 0


def assess(row, now, policy):
    today = now.astimezone(TAIPEI).date()
    symbol = row.get("stock_id")
    if not valid_symbol(symbol):
        # An invalid identity cannot safely be displayed as an API-selectable symbol.
        raise SourceError("Invalid catalogue identity")
    reasons = []
    name = row.get("stock_name")
    market = row.get("market")
    if not isinstance(name, str) or not name.strip() or len(name) > 100 or market not in ("twse", "tpex"):
        reasons.append("INVALID_METADATA")
    last_seen = None
    try:
        seen = batch_date(row.get("last_seen_at"), now)
        latest = batch_date(row.get("latest_list_batch"), now)
        last_seen = seen.isoformat(timespec="seconds")
        if seen != latest:
            reasons.append("NOT_LATEST_LIST_BATCH")
        if (today - latest.date()).days > policy.max_list_age_days:
            reasons.append("STALE_LIST")
    except (TypeError, ValueError):
        reasons.append("INVALID_LIST_DATE")
    start = end = None
    observations = 0
    try:
        raw_count = row.get("observations")
        if raw_count is None or raw_count == 0:
            reasons.append("NO_PRICES")
        else:
            if isinstance(raw_count, bool) or int(raw_count) != raw_count or raw_count < 0:
                raise ValueError("Bad count")
            observations = int(raw_count)
            start = source_date(row.get("source_start"), today)
            end = source_date(row.get("source_end"), today)
            if end < start or row.get("invalid_prices") != 0 or not all(
                finite_positive(row.get(key)) for key in ("first_price", "last_price")
            ):
                raise ValueError("Bad prices")
            if (end - start).days < policy.min_history_days or observations < policy.min_observations:
                reasons.append("INSUFFICIENT_HISTORY")
            if (today - end).days > policy.max_price_age_days:
                reasons.append("STALE_PRICES")
    except (TypeError, ValueError, OverflowError):
        reasons.append("INVALID_PRICES")
    return {
        "symbol": symbol, "name": name if isinstance(name, str) and name.strip() and len(name) <= 100 else "名稱待確認",
        "market": market if market in ("twse", "tpex") else "unknown",
        "eligible": not reasons, "reasons": reasons,
        "reasonText": "；".join(REASONS[r] for r in reasons),
        "priceStart": start.isoformat() if start else None,
        "priceEnd": end.isoformat() if end else None,
        "observations": observations, "lastSeenAt": last_seen,
    }


def build_catalog(rows, now=None, policy=None):
    now = now or datetime.now(TAIPEI)
    policy = policy or Policy()
    if now.tzinfo is None or len(rows) > MAX_ITEMS:
        raise SourceError("Invalid clock or catalogue exceeds configured bound")
    items = sorted((assess(row, now, policy) for row in rows), key=lambda r: r["symbol"])
    if len({r["symbol"] for r in items}) != len(items):
        raise SourceError("Duplicate catalogue identity")
    identity = json.dumps({"items": items, "policy": asdict(policy)}, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return {
        "schemaVersion": 2, "catalogId": "catalog2-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        "queriedAt": now.astimezone(TAIPEI).isoformat(timespec="seconds"),
        "total": len(items), "eligibleCount": sum(r["eligible"] for r in items),
        "policy": asdict(policy), "items": items,
    }


def price_sql(selected=False):
    # Only a fixed, internal query shape changes. User symbols are bound parameters.
    price_filter = "WHERE stock_id=%s" if selected else ""
    list_filter = "WHERE l.stock_id=%s" if selected else ""
    return f"""
WITH periods AS (
 SELECT stock_id, MIN(`date`) AS source_start, MAX(`date`) AS source_end,
 COUNT(*) AS observations, SUM(adj_close IS NULL OR adj_close<=0) AS invalid_prices
 FROM etf.etf_price {price_filter} GROUP BY stock_id
)
SELECT l.stock_id,l.stock_name,l.market,l.last_seen_at,
 (SELECT MAX(last_seen_at) FROM stock.etf_list) AS latest_list_batch,
 p.source_start,p.source_end,p.observations,p.invalid_prices,
 f.adj_close AS first_price,z.adj_close AS last_price
FROM stock.etf_list l
LEFT JOIN periods p ON p.stock_id=l.stock_id
LEFT JOIN etf.etf_price f ON f.stock_id=p.stock_id AND f.`date`=p.source_start
LEFT JOIN etf.etf_price z ON z.stock_id=p.stock_id AND z.`date`=p.source_end
{list_filter}
ORDER BY l.stock_id LIMIT {MAX_ITEMS + 1}
"""
