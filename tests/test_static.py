import json

import pytest

from backend import analysis, service, store
from backend.demo_source import DemoSource
from backend.sheets import parse_rows
from backend.store_source import StoreSource


@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path / "store")
    return tmp_path / "store"


@pytest.fixture()
def demo():
    src = DemoSource()
    service.set_source(src)
    yield src
    service.set_source(None)


def test_store_roundtrip(tmp_store):
    cells = analysis.grid_cells(store.REGIONS["gediz"]["polygon"])
    st = store.new_store("gediz", "gee", [{**c, "crop": 0.5} for c in cells])
    store.set_month(st, "2020-05", [0.123456] + [None] * (len(cells) - 1))
    store.save(st)
    back = store.load("gediz")
    assert store.is_current(back, "gediz")
    assert back["months"]["2020-05"][0] == 0.1235
    assert store.latest_key(back) == "2020-05"
    assert set(store.load_all()) == {"gediz"}


def test_store_source_basics(demo):
    m = demo.region_map("konya", 2021, 5)
    vcis = [f["properties"]["vci"] for f in m["features"] if f["properties"]["vci"] is not None]
    assert vcis and all(0 <= v <= 100 for v in vcis)
    assert demo.coverage()["complete"]
    assert demo.point_monthly(41.0, 29.0) == []  # İstanbul: izlenen alan dışında
    series = demo.region_monthly("menderes")
    assert series[-1]["t"] == "%d-%02d" % demo.latest() and series[-1]["ndvi"] is not None


def test_store_source_requires_every_region_to_have_data(tmp_store):
    st = store.new_store("konya", "gee", [{"id": "a", "lat": 38, "lon": 33, "bbox": [32.9, 37.9, 33.1, 38.1], "crop": 1}])
    with pytest.raises(ValueError):
        StoreSource({"konya": st})


def test_build_site_demo(tmp_path, demo):
    from scripts.build_site import build

    out = tmp_path / "site"
    res = build(out, force_demo=True, with_raster=False)
    assert res["mode"] == "demo" and res["maps"] > 300
    status = json.loads((out / "api/status.json").read_text(encoding="utf-8"))
    assert status["static"] and status["point_scale"] == "cell"
    assert "window.KG_STATIC = true" in (out / "index.html").read_text(encoding="utf-8")
    y, m = status["latest"]["year"], status["latest"]["month"]
    feat = json.loads((out / f"api/map/konya/{y}-{m:02d}.json").read_text(encoding="utf-8"))["features"][0]
    cell = json.loads((out / f"api/cell/konya/{feat['properties']['id']}.json").read_text(encoding="utf-8"))
    assert cell["current"]["vci"] == feat["properties"]["vci"]
    assert (out / "static/app.js").exists() and (out / "api/drought-history/gediz/7.json").exists()
    # Demo yayında uyarı listesi boş olmalı (gerçek uyarılar karışmasın)
    assert json.loads((out / "api/alerts.json").read_text(encoding="utf-8")) == []


def test_parse_form_rows():
    rows = [
        ["Zaman damgası", "Ad Soyad", "E-posta adresi", "Tarla adı", "Enlem", "Boylam", "Uyarı eşiği", "KVKK onayı"],
        ["1", "Ayşe Kaya", "a@x.com", "Ova", "37,85", "32.6", "35 – orta ve üzeri", "Evet"],
        ["2", "Onaysız", "b@x.com", "", "37.8", "32.6", "", ""],          # onay yok → atlanır
        ["3", "Yanlış", "c@x.com", "", "52.1", "13.4", "20", "Evet"],      # Türkiye dışı → atlanır
        ["4", "Eşiksiz", "", "", "38.5", "28.1", "", "Evet"],
    ]
    subs = parse_rows(rows)
    assert [s["name"] for s in subs] == ["Ayşe Kaya", "Eşiksiz"]
    assert subs[0]["lat"] == 37.85 and subs[0]["threshold"] == 35 and subs[0]["field_name"] == "Ova"
    assert subs[1]["email"] is None and subs[1]["threshold"] == 35.0


def test_send_alerts_once_per_period(demo, monkeypatch):
    from backend import analysis
    from scripts.send_alerts import process

    monkeypatch.setattr(analysis, "in_season", lambda m, p: True)  # mevsim içiymiş gibi
    sub = {"name": "Test", "email": "t@example.com", "lat": 37.6, "lon": 32.8, "field_name": None, "threshold": 99}
    sent = []
    state = {"sent": {}, "public": []}
    new = process([sub], state, send=lambda to, subj, body: sent.append(subj) or True)
    assert len(new) == 1
    assert sent[0].endswith("aboneliğiniz alındı") and sent[1].startswith("Kuraklık uyarısı")
    assert "t@example.com" not in json.dumps(state) and "Test" not in json.dumps(state["public"])
    sent.clear()
    assert process([sub], state, send=lambda *a: sent.append(a) or True) == []  # aynı dönem: tekrar gönderilmez
    assert sent == []  # hoş geldin de tekrar gitmez

    def boom(*a):
        raise OSError("smtp kapalı")
    state2 = {"sent": {}, "public": []}
    assert process([sub], state2, send=boom) == []
    assert state2["sent"] == {} and state2["welcomed"] == []  # hata → sonra tekrar denenir


def test_no_drought_alert_outside_growing_season(demo, monkeypatch):
    from backend import analysis
    from scripts.send_alerts import process

    monkeypatch.setattr(analysis, "in_season", lambda m, p: False)  # hasat sonrası
    sub = {"name": "Test", "email": "t@example.com", "lat": 37.6, "lon": 32.8, "field_name": "Ova", "threshold": 99}
    bodies = []
    state = {"sent": {}, "public": []}
    assert process([sub], state, send=lambda to, subj, body: bodies.append(body) or True) == []
    assert len(bodies) == 1 and "aboneliğiniz alındı" in bodies[0] and "Ova" in bodies[0]


def test_in_season():
    from backend.analysis import in_season, season_label

    assert [m for m in range(1, 13) if in_season(m, 5)] == [3, 4, 5, 6]
    assert [m for m in range(1, 13) if in_season(m, 1)] == [1, 2, 11, 12]
    assert season_label(5) == "Mart–Haziran"


def test_update_data_with_fake_gee(tmp_store, monkeypatch):
    """Sahte bir Earth Engine ile aylık güncelleme döngüsü: eksik aylar çekilir, hata veren ay sonraya kalır."""
    import backend.gee_source as gs
    from scripts import update_data

    calls = []

    class FakeGEE:
        def crop_fractions(self, rid, cells):
            return [0.6] * len(cells)

        def grid_month(self, rid, y, m, cells):
            calls.append((rid, y, m))
            if (rid, y, m) == ("gediz", 2019, 7):
                raise RuntimeError("Computation timed out")
            return [0.2 + m / 100] * len(cells)

    monkeypatch.setattr(gs, "GEESource", FakeGEE)
    monkeypatch.setattr(update_data, "_with_retry", lambda fn, *a, **k: fn(*a))
    monkeypatch.setattr("sys.argv", ["update_data", "--regions", "gediz", "--workers", "2"])
    update_data.main()
    st = store.load("gediz")
    assert "2019-07" not in st["months"] and "2019-06" in st["months"]
    n = len(st["months"])
    # İkinci çalıştırma: sadece eksik ay + son 2 ay yenilenir
    calls.clear()
    update_data.main()
    assert len(calls) == 3 and ("gediz", 2019, 7) in calls
    assert len(store.load("gediz")["months"]) == n


def test_update_data_time_limit_keeps_regions_in_step(tmp_store, monkeypatch):
    """Süre erken biterse bile her bölgenin en güncel ayı çekilmiş olmalı (site demoya düşmesin)."""
    import itertools

    import backend.gee_source as gs
    from backend.sources_common import latest_month
    from scripts import update_data

    class FakeGEE:
        def crop_fractions(self, rid, cells):
            return [1.0] * len(cells)

        def grid_month(self, rid, y, m, cells):
            return [0.3] * len(cells)

    clock = itertools.count(0, 60)  # her çağrıda 1 dakika geçmiş gibi
    monkeypatch.setattr(gs, "GEESource", FakeGEE)
    monkeypatch.setattr(update_data.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr("sys.argv", ["update_data", "--max-minutes", "5", "--workers", "1"])
    update_data.main()
    latest = "%d-%02d" % latest_month()
    for rid in store.REGIONS:
        st = store.load(rid)
        assert latest in st["months"], rid
        assert len(st["months"]) <= 2
