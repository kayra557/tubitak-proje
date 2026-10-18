import os

import pytest

os.environ["DATA_MODE"] = "demo"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import config, service
    from backend.demo_source import DemoSource
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    # Repoda gerçek veri (data/store) olsa bile testler yapay veriyle çalışsın
    service.set_source(DemoSource())
    from backend.app import app
    yield app.test_client()
    service.set_source(None)


def test_status_and_regions(client):
    assert client.get("/api/status").json["mode"] == "demo"
    ids = {r["id"] for r in client.get("/api/regions").json}
    assert ids == {"konya", "gediz", "menderes"}


def test_map(client):
    d = client.get("/api/map?region=konya&year=2021&month=5").json
    assert d["features"] and d["summary"]["drought_percent"] > 50  # 2021 kurak yıl
    assert client.get("/api/map?region=yok").status_code == 400
    assert client.get("/api/map?year=2099&month=1").status_code == 400


def test_timeseries_and_point(client):
    ts = client.get("/api/timeseries?region=gediz").json
    assert ts["trend"]["slope"] < 0
    p = client.get("/api/point?lat=37.9&lon=32.6").json
    assert p["region"] == "konya" and p["current"]["vci"] is not None and p["advice"]
    assert client.get("/api/point?lat=60&lon=10").status_code == 400


def test_subscription_and_alert_flow(client):
    r = client.post("/api/subscriptions", json={"name": "Test Çiftçi", "email": "t@example.com",
                                                "lat": 37.6, "lon": 32.8, "threshold": 80})
    assert r.status_code == 201
    assert client.get("/api/subscriptions").json[0]["email"].startswith("t***@")
    first = client.post("/api/alerts/check").json
    assert len(first["new_alerts"]) == 1
    # Aynı dönem için ikinci kez uyarı üretilmez
    assert client.post("/api/alerts/check").json["new_alerts"] == []
    assert client.get("/api/alerts").json[0]["delivered"] == "site"
    sid = r.json["id"]
    assert client.delete(f"/api/subscriptions/{sid}").json["deleted"]
    assert client.post("/api/subscriptions", json={"name": "", "lat": 37, "lon": 32}).status_code == 400
