"""Google Formu ile abone olan çiftçilere kuraklık uyarısı gönderir (aylık, GitHub Actions'ta).

Gerekenler (ortam değişkenleri):
    ABONE_SHEET_ID  – form yanıt tablosunun kimliği (docs.google.com/spreadsheets/d/<KİMLİK>/...)
    GEE_KEY_FILE    – servis hesabı anahtarı (tabloyu okumak için de kullanılır)
    SMTP_*          – e-posta ayarları (yoksa e-posta gönderilmez, sadece sitedeki listeye yazılır)

Kişisel veri repoya yazılmaz: kime gönderildiği yalnızca tek yönlü özet (hash) olarak saklanır,
sitede gösterilen uyarı listesinde isim/e-posta yoktur.
"""
import datetime as dt
import hashlib
import json
import logging
import os

from backend import alerts, places, service, store
from backend.config import GEE_KEY_FILE
from backend.sheets import read_subscribers
from backend.store_source import StoreSource

log = logging.getLogger("send_alerts")
STATE = store.STORE_DIR / "alerts_state.json"


def _key(sub: dict) -> str:
    raw = f"{(sub.get('email') or '').lower()}|{sub['lat']:.4f}|{sub['lon']:.4f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"sent": {}, "public": []}


def process(subs: list[dict], state: dict, send=alerts.send_email) -> list[dict]:
    """Eşik altındaki her abone için (dönem başına bir kez) uyarı gönderir; yeni uyarıları döner."""
    new = []
    for sub in subs:
        report = service.point_report(sub["lat"], sub["lon"])
        cur = report.get("current")
        if not alerts.needs_alert(sub, cur):
            continue
        k = _key(sub)
        if state["sent"].get(k) == cur["t"]:
            continue  # bu dönem için zaten gönderildi
        subject, message = alerts.alert_message(sub, cur, report)
        try:
            delivered = "e-posta" if send(sub.get("email"), subject, message) else "site"
        except Exception as exc:
            log.warning("E-posta gönderilemedi: %s", exc)
            continue  # gönderilmediyse kaydetme; sonraki çalıştırmada tekrar denenir
        state["sent"][k] = cur["t"]
        np = places.nearest(sub["lat"], sub["lon"])
        entry = {"period": cur["t"], "place": f"{np['name']} ({np['province']}) yakını",
                 "class": cur["class"], "class_label": cur["class_label"], "vci": cur["vci"],
                 "delivered": delivered, "date": dt.date.today().isoformat()}
        state["public"].insert(0, entry)
        new.append(entry)
    state["public"] = state["public"][:100]
    return new


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sheet_id = os.environ.get("ABONE_SHEET_ID")
    if not sheet_id or not GEE_KEY_FILE:
        log.info("ABONE_SHEET_ID veya GEE anahtarı yok; uyarı kontrolü atlandı.")
        return
    stores = store.load_all()
    if not stores:
        log.info("Depoda uydu verisi yok; uyarı kontrolü atlandı.")
        return
    service.set_source(StoreSource(stores))
    subs = read_subscribers(sheet_id, GEE_KEY_FILE)
    state = load_state()
    new = process(subs, state)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("%d abone kontrol edildi, %d yeni uyarı.", len(subs), len(new))


if __name__ == "__main__":
    main()
