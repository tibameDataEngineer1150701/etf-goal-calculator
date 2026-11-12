"""Synthetic local test inputs. They are never an API production fallback."""
import copy
import json
from datetime import datetime
from pathlib import Path
from snapshot import TAIPEI

NOW = datetime(2026, 11, 12, 12, tzinfo=TAIPEI)


def inputs():
    old = json.loads((Path(__file__).parent / "fixtures/v3-contract.json").read_text(encoding="utf-8"))["snapshot"]
    etfs = []
    for r in old["etfs"]:
        etfs.append({
            "stock_id": r["symbol"], "stock_name": r["name"], "market": "twse",
            "last_seen_at": "2026-11-12T09:00:00", "latest_list_batch": "2026-11-12T09:00:00",
            "source_start": r["priceStart"], "source_end": r["priceEnd"],
            "observations": r["observations"], "invalid_prices": 0,
            "first_price": r["first"], "last_price": r["last"],
        })
    extra = dict(etfs[0], stock_id="00900", stock_name="測試新增 ETF", first_price=100, last_price=121,
                 source_start="2024-11-09", source_end="2026-11-09", observations=480)
    etfs.extend([
        extra,
        dict(extra, stock_id="00901", stock_name="測試尚無價格", observations=None, source_start=None, source_end=None, first_price=None, last_price=None),
        dict(extra, stock_id="00902", stock_name="測試期間不足", source_start="2026-10-01", observations=20),
        dict(extra, stock_id="00903", stock_name="測試價格過舊", source_end="2026-10-01"),
        dict(extra, stock_id="00904", stock_name="測試舊清單", last_seen_at="2026-10-01T09:00:00"),
    ])
    houses = []
    for r in old["houses"]:
        for kind, key in (("成屋買賣", "existing"), ("預售屋買賣", "presale")):
            houses.append(dict(region=r["city"], transaction_type=kind, house_period=old["housePeriod"],
                hpi_period=old["hpiPeriod"], anchor_count=1, txn_count=1, hpi_count=1, hpi5_count=1, hpi10_count=1,
                unit_price=r[key], transaction_count=r[key + "Count"], current_hpi=r["hpi"], hpi5=r["hpi5"], hpi10=r["hpi10"]))
    return copy.deepcopy(etfs), copy.deepcopy(houses)
