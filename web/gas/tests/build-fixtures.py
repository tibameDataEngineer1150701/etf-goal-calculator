"""Generate local test envelopes, never connect to external services."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from catalog import Policy, assess, build_catalog
from fixtures import NOW, inputs
from snapshot import build_snapshot

rows, houses = inputs()
catalog = build_catalog(rows, NOW)
snapshots = {}
for row in rows:
    entry = assess(row, NOW, Policy())
    if entry["eligible"]:
        snapshots[row["stock_id"]] = {"mode": "LIVE", "snapshot": build_snapshot([row], houses, NOW, entry)}
out = ROOT / "verification"
out.mkdir(exist_ok=True)
(out / "local-fixtures.json").write_text(json.dumps({"testOnly": True, "catalog": catalog, "snapshots": snapshots}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Generated synthetic local catalogue and single-symbol fixtures; no cloud access.")
