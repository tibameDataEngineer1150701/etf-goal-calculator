"""Read-only source contract shared with the existing GAS calculator."""

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone


CITIES = ("臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市")
NORMALIZE = {"台北市": "臺北市", "台中市": "臺中市", "台南市": "臺南市"}
TAIPEI = timezone(timedelta(hours=8))


class SourceError(ValueError):
    """A source cannot safely be used by the calculator."""


def positive(value, label):
    if value is None or isinstance(value, bool):
        raise SourceError(label)
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise SourceError(label) from exc
    if not math.isfinite(number) or number <= 0:
        raise SourceError(label)
    return number


def count(value, label):
    number = positive(value, label)
    if not number.is_integer():
        raise SourceError(label)
    return int(number)


def quarter(value, today):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}Q[1-4]", value):
        raise SourceError("Invalid quarter")
    if value > f"{today.year}Q{(today.month - 1) // 3 + 1}":
        raise SourceError("Future quarter")
    return value


def source_date(value, today):
    try:
        # A DATETIME is not silently truncated to a date.
        result = date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise SourceError("Invalid source date") from exc
    if result > today:
        raise SourceError("Future source date")
    return result


def build_snapshot(etf_rows, housing_rows, now=None, eligibility=None):
    now = now or datetime.now(TAIPEI)
    if now.tzinfo is None:
        raise SourceError("Query clock needs timezone")
    now = now.astimezone(TAIPEI)
    today = now.date()
    etfs = {}
    for row in etf_rows:
        symbol = row["stock_id"]
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9][A-Z0-9]{3,19}", symbol) or symbol in etfs:
            raise SourceError("Unexpected or duplicate ETF")
        start = source_date(row["source_start"], today)
        end = source_date(row["source_end"], today)
        observations = count(row["observations"], "Invalid price observation count")
        if (end - start).days < 365 or observations < 240 or row["invalid_prices"] != 0:
            raise SourceError("Insufficient history or invalid prices")
        name = row.get("stock_name")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise SourceError("Missing ETF name in current list")
        etfs[symbol] = {
            "symbol": symbol, "name": name,
            "first": positive(row["first_price"], "Invalid first price"),
            "last": positive(row["last_price"], "Invalid last price"),
            "observations": observations,
            "priceStart": start.isoformat(), "priceEnd": end.isoformat(),
        }
    if len(etfs) != 1:
        raise SourceError("Expected exactly one selected ETF")

    houses = {}
    periods = set()
    for row in housing_rows:
        city = NORMALIZE.get(row["region"], row["region"])
        kind = {"成屋買賣": "existing", "預售屋買賣": "presale"}.get(row["transaction_type"])
        if city not in CITIES or kind is None:
            raise SourceError("Unexpected city or transaction type")
        if any(row.get(key) != 1 for key in ("anchor_count", "txn_count", "hpi_count", "hpi5_count", "hpi10_count")):
            raise SourceError("Missing or duplicate housing/HPI source")
        house_period = quarter(row["house_period"], today)
        hpi_period = quarter(row["hpi_period"], today)
        periods.add((house_period, hpi_period))
        values = {
            "hpi": positive(row["current_hpi"], "Invalid current HPI"),
            "hpi5": positive(row["hpi5"], "Invalid five-year HPI"),
            "hpi10": positive(row["hpi10"], "Invalid ten-year HPI"),
        }
        house = houses.setdefault(city, {"city": city, **values})
        if kind in house or any(house[key] != value for key, value in values.items()):
            raise SourceError("Duplicate or inconsistent city input")
        house[kind] = positive(row["unit_price"], "Invalid median unit price")
        house[kind + "Count"] = count(row["transaction_count"], "Invalid transaction count")
    if set(houses) != set(CITIES) or len(periods) != 1:
        raise SourceError("Missing city or mixed source periods")
    if any("existing" not in house or "presale" not in house for house in houses.values()):
        raise SourceError("Missing transaction type")
    house_period, hpi_period = periods.pop()
    snapshot = {
        "schemaVersion": 2, "capturedDate": today.isoformat(),
        "housePeriod": house_period, "hpiPeriod": hpi_period,
        "hpi5Period": str(int(hpi_period[:4]) - 5) + hpi_period[4:],
        "hpi10Period": str(int(hpi_period[:4]) - 10) + hpi_period[4:],
        "priceStart": min(row["priceStart"] for row in etfs.values()),
        "priceEnd": max(row["priceEnd"] for row in etfs.values()),
        "etfs": list(etfs.values()),
        "houses": [houses[city] for city in CITIES],
        "eligibility": eligibility,
    }
    identity = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    snapshot["id"] = "mysql2-" + hashlib.sha256(identity).hexdigest()[:24]
    # Query time must not be called source update time. It is excluded from the content ID.
    snapshot["queriedAt"] = now.isoformat(timespec="seconds")
    return snapshot


HOUSING_SQL = """
WITH anchor AS (
 SELECT region, transaction_type, MAX(house_price_period) AS house_period,
 MAX(growth_period) AS hpi_period, COUNT(*) AS anchor_count
 FROM housing.down_pmt_target WHERE scenario=%s
 GROUP BY region,transaction_type
), txn AS (
 SELECT period,municipality,transaction_type,MAX(median_unit_price) AS unit_price,
 MAX(transaction_count) AS transaction_count,COUNT(*) AS row_count
 FROM housing.housing_txn_qtr GROUP BY period,municipality,transaction_type
), hpi AS (
 SELECT period,region,MAX(housing_price_index) AS idx,COUNT(*) AS row_count
 FROM housing.housing_price_index GROUP BY period,region
)
SELECT a.*,t.unit_price,t.transaction_count,t.row_count AS txn_count,
 h.idx AS current_hpi,h.row_count AS hpi_count,
 b.idx AS hpi5,b.row_count AS hpi5_count,c.idx AS hpi10,c.row_count AS hpi10_count
FROM anchor a
LEFT JOIN txn t ON t.period=a.house_period AND t.municipality=a.region AND t.transaction_type=a.transaction_type
LEFT JOIN hpi h ON h.period=a.hpi_period AND h.region=a.region
LEFT JOIN hpi b ON b.region=a.region AND b.period=CONCAT(CAST(LEFT(a.hpi_period,4) AS UNSIGNED)-5,RIGHT(a.hpi_period,2))
LEFT JOIN hpi c ON c.region=a.region AND c.period=CONCAT(CAST(LEFT(a.hpi_period,4) AS UNSIGNED)-10,RIGHT(a.hpi_period,2))
ORDER BY a.region,a.transaction_type
"""
