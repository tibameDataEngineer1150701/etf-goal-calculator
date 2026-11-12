import copy
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from catalog import MAX_ITEMS, Policy, assess, build_catalog, price_sql
from fixtures import NOW, inputs
from main import BoundedReader, NotFound, Settings, Unavailable, create_app, read_source
from snapshot import SourceError, TAIPEI, build_snapshot

TOKEN = "local-test-only-" * 4
HEADERS = {"Authorization": "Bearer " + TOKEN}


def client_with(rows=None):
    original, houses = inputs()
    rows = original if rows is None else rows
    calls = []
    def catalog(_):
        calls.append("catalog")
        return build_catalog(rows, NOW)
    def snapshot(symbol):
        calls.append(symbol)
        found = [r for r in rows if r["stock_id"] == symbol]
        if not found:
            raise NotFound()
        e = assess(found[0], NOW, Policy())
        if not e["eligible"]:
            raise Unavailable(e)
        return build_snapshot(found, houses, NOW, e)
    catalog_reader = BoundedReader(catalog)
    snapshots = BoundedReader(snapshot)
    return TestClient(create_app(SimpleNamespace(token=TOKEN), catalog_reader, snapshots)), calls, catalog_reader, snapshots


def test_dynamic_catalogue_and_individual_disabling():
    rows, _ = inputs()
    c = build_catalog(rows, NOW)
    assert c["total"] == 8 and c["eligibleCount"] == 4
    assert next(x for x in c["items"] if x["symbol"] == "00900")["eligible"]
    expected = {"00901": "NO_PRICES", "00902": "INSUFFICIENT_HISTORY", "00903": "STALE_PRICES", "00904": "NOT_LATEST_LIST_BATCH"}
    for item in c["items"]:
        if item["symbol"] in expected:
            assert item["reasons"] == [expected[item["symbol"]]] and not item["eligible"]
    rows.append(dict(rows[3], stock_id="00999"))
    assert build_catalog(rows, NOW)["eligibleCount"] == 5
    assert build_catalog([], NOW)["items"] == []


@pytest.mark.parametrize("field,value,reason", [
    ("first_price", 0, "INVALID_PRICES"), ("last_price", float("inf"), "INVALID_PRICES"),
    ("first_price", True, "INVALID_PRICES"), ("invalid_prices", 1, "INVALID_PRICES"),
    ("source_start", "2025-02-30", "INVALID_PRICES"), ("source_end", "2026-11-13", "INVALID_PRICES"),
    ("source_start", "2026-11-12", "INVALID_PRICES"), ("observations", 239, "INSUFFICIENT_HISTORY"),
    ("observations", 1.5, "INVALID_PRICES"), ("stock_name", "", "INVALID_METADATA"),
    ("market", "unknown", "INVALID_METADATA"), ("last_seen_at", None, "INVALID_LIST_DATE"),
    ("last_seen_at", "2026-11-13", "INVALID_LIST_DATE"),
    ("last_seen_at", "2026-11-12T12:00:01+08:00", "INVALID_LIST_DATE"),
])
def test_bad_row_does_not_block_other_etfs(field, value, reason):
    rows, _ = inputs()
    rows[0][field] = value
    c = build_catalog(rows, NOW)
    assert reason in c["items"][0]["reasons"]
    assert c["eligibleCount"] == 3


def test_thresholds_and_policy_identity():
    rows, _ = inputs()
    r = dict(rows[0], source_start="2025-11-09", source_end="2026-11-09", observations=240)
    assert assess(r, NOW, Policy())["eligible"]
    r["source_start"] = "2025-11-10"
    assert "INSUFFICIENT_HISTORY" in assess(r, NOW, Policy())["reasons"]
    r.update(last_seen_at="2026-09-01T09:00:00", latest_list_batch="2026-09-01T09:00:00")
    assert "STALE_LIST" in assess(r, NOW, Policy())["reasons"]
    assert build_catalog(rows, NOW)["catalogId"] != build_catalog(rows, NOW, replace(Policy(), max_price_age_days=20))["catalogId"]
    with pytest.raises(ValueError):
        Policy(max_price_age_days=0)


def test_duplicate_corrupt_identity_and_catalogue_overflow_fail_closed():
    rows, _ = inputs()
    for bad in [rows + [rows[0]], [dict(rows[0], stock_id="' OR 1=1")], [rows[0]] * (MAX_ITEMS + 1)]:
        with pytest.raises(SourceError):
            build_catalog(bad, NOW)


def test_authentication_precedes_reads_and_no_public_write_routes():
    client, calls, _, _ = client_with()
    for path in ["/v2/etfs", "/v2/snapshot?symbol=00900"]:
        for h in [{}, {"Authorization": "Bearer incorrect"}]:
            assert client.get(path, headers=h).status_code == 401
    assert calls == []
    assert client.get("/health/live").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/v1/snapshot", headers=HEADERS).status_code == 404
    assert client.post("/v2/snapshot?symbol=00900", headers=HEADERS).status_code == 405


def test_pagination_version_empty_and_limit():
    client, _, reader, _ = client_with()
    first = client.get("/v2/etfs?limit=3", headers=HEADERS)
    assert first.headers["cache-control"] == "no-store"
    c = first.json()["catalog"]
    second = client.get("/v2/etfs", params={"offset": 3, "limit": 3, "catalog_id": c["catalogId"]}, headers=HEADERS).json()["catalog"]
    assert len(second["items"]) == 3 and second["nextOffset"] == 6
    assert client.get("/v2/etfs?catalog_id=catalog2-old", headers=HEADERS).status_code == 409
    for args in ["limit=101", "offset=-1", "limit=0", "offset=2001"]:
        assert client.get("/v2/etfs?" + args, headers=HEADERS).status_code == 422
    empty, *_ = client_with([])
    assert empty.get("/v2/etfs", headers=HEADERS).json()["catalog"]["total"] == 0


def test_selected_symbol_period_identity_and_unavailable_not_replaced():
    client, _, _, _ = client_with()
    r = client.get("/v2/snapshot?symbol=00900", headers=HEADERS)
    s = r.json()["snapshot"]
    assert r.status_code == 200 and s["schemaVersion"] == 2
    assert len(s["etfs"]) == 1 and s["etfs"][0]["symbol"] == "00900"
    assert s["etfs"][0]["priceStart"] == "2024-11-09"
    assert s["etfs"][0]["last"] == 121
    for symbol in ["00901", "00902", "00903", "00904"]:
        response = client.get("/v2/snapshot", params={"symbol": symbol}, headers=HEADERS)
        assert response.status_code == 422 and "snapshot" not in response.json()
    assert client.get("/v2/snapshot?symbol=9999", headers=HEADERS).status_code == 404
    assert client.get("/v2/snapshot", params={"symbol": "0050' OR 1=1"}, headers=HEADERS).status_code == 400


def test_housing_validation_kept():
    rows, houses = inputs()
    for changed in [houses[:-1], houses + [houses[0]], [dict(houses[0], current_hpi=0)] + houses[1:]]:
        with pytest.raises(SourceError):
            build_snapshot(rows[:1], changed, NOW, assess(rows[0], NOW, Policy()))


def test_cache_bound_expiry_and_no_secret_error_leak():
    state = {"fail": False}
    def read(key):
        if state["fail"]:
            raise RuntimeError("password=secret SQL private-address")
        return {"key": key}
    reader = BoundedReader(read, ttl=60, capacity=2)
    for key in ["a", "b", "c"]:
        reader.get(key)
    assert len(reader.values) == 2 and "a" not in reader.values
    x = reader.get("c"); x["key"] = "mutated"
    assert reader.get("c")["key"] == "c"
    reader.values["c"] = (0, {"key": "expired"})
    state["fail"] = True
    with pytest.raises(RuntimeError):
        reader.get("c")
    client = TestClient(create_app(SimpleNamespace(token=TOKEN), reader, reader))
    response = client.get("/v2/snapshot?symbol=00900", headers=HEADERS)
    assert response.status_code == 503
    assert "secret" not in response.text and "SQL" not in response.text


def test_mysql_readonly_and_parameter_binding(monkeypatch):
    rows, houses = inputs()
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args=None): calls.append((sql, args))
        def fetchall(self): return rows[3:4] if "WITH periods" in calls[-1][0] else houses
    class Conn:
        def cursor(self): return Cursor()
        def rollback(self): calls.append(("ROLLBACK", None))
        def close(self): calls.append(("CLOSE", None))
    monkeypatch.setattr("main.pymysql.connect", lambda **kwargs: Conn())
    class Clock:
        @staticmethod
        def now(tz): return NOW
    monkeypatch.setattr("main.datetime", Clock)
    settings = SimpleNamespace(host="test", user="readonly", password="test", policy=Policy())
    result = read_source(settings, "00900")
    assert result["etfs"][0]["symbol"] == "00900"
    assert "READ ONLY" in calls[2][0] and "REPEATABLE READ" in calls[1][0]
    assert calls[3][1] == ("00900", "00900") and "00900" not in calls[3][0]
    assert [c[0] for c in calls[-2:]] == ["ROLLBACK", "CLOSE"]
    assert "LIMIT 2001" in price_sql()


def test_selected_source_rechecks_eligibility_and_always_rolls_back(monkeypatch):
    rows, _ = inputs()
    # The catalogue was eligible; the selected read now sees invalid data.
    assert assess(rows[3], NOW, Policy())["eligible"]
    changed = dict(rows[3], invalid_prices=1)
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args=None): calls.append(sql)
        def fetchall(self): return [changed]
    class Conn:
        def cursor(self): return Cursor()
        def rollback(self): calls.append("ROLLBACK")
        def close(self): calls.append("CLOSE")
    monkeypatch.setattr("main.pymysql.connect", lambda **kwargs: Conn())
    class Clock:
        @staticmethod
        def now(tz): return NOW
    monkeypatch.setattr("main.datetime", Clock)
    settings = SimpleNamespace(host="test", user="readonly", password="test", policy=Policy())
    with pytest.raises(Unavailable) as exc:
        read_source(settings, "00900")
    assert "INVALID_PRICES" in exc.value.entry["reasons"]
    assert calls[-2:] == ["ROLLBACK", "CLOSE"]
    assert not any("WITH anchor" in c for c in calls)
    calls.clear()
    with pytest.raises(SourceError):
        read_source(settings, "00900' OR 1=1")
    assert calls == []


def test_settings_reject_root_and_weak_token(tmp_path, monkeypatch):
    token, password = tmp_path / "token", tmp_path / "password"
    token.write_text(TOKEN); password.write_text("local-only")
    monkeypatch.setenv("API_TOKEN_FILE", str(token)); monkeypatch.setenv("MYSQL_PASSWORD_FILE", str(password))
    monkeypatch.setenv("MYSQL_USER", "root")
    with pytest.raises(ValueError): Settings()
    monkeypatch.setenv("MYSQL_USER", "etf_web_readonly")
    assert Settings().policy.max_price_age_days == 14
    token.write_text("short")
    with pytest.raises(ValueError): Settings()


def test_team_rate_limit_and_recovery(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('main.time', SimpleNamespace(monotonic=lambda: clock[0]))
    client, calls, _, _ = client_with()
    for _ in range(120):
        assert client.get('/v2/etfs', headers=HEADERS).status_code == 200
    response = client.get('/v2/etfs', headers=HEADERS)
    assert response.status_code == 429 and response.headers['retry-after'] == '60'
    assert calls == ['catalog']
    assert client.get('/v2/etfs').status_code == 401
    assert client.get('/health/live').status_code == 200
    clock[0] = 160.01
    assert client.get('/v2/etfs', headers=HEADERS).status_code == 200
