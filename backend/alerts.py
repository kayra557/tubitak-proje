"""Çiftçi abonelikleri ve kuraklık uyarıları (SQLite + isteğe bağlı e-posta)."""
from __future__ import annotations

import datetime as dt
import logging
import smtplib
import sqlite3
from email.message import EmailMessage

from . import config, service

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    field_name TEXT,
    threshold REAL NOT NULL DEFAULT 35,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    ndvi REAL,
    vci REAL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    delivered TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(subscription_id, period)
);
"""


def _db():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def add_subscription(name: str, email: str | None, lat: float, lon: float,
                     field_name: str | None = None, threshold: float = 35) -> dict:
    with _db() as con:
        cur = con.execute(
            "INSERT INTO subscriptions(name, email, lat, lon, field_name, threshold, created_at) "
            "VALUES (?,?,?,?,?,?,?)", (name, email, lat, lon, field_name, threshold, _now()))
        sid = cur.lastrowid
    return get_subscription(sid)


def get_subscription(sid: int) -> dict | None:
    with _db() as con:
        row = con.execute("SELECT * FROM subscriptions WHERE id=?", (sid,)).fetchone()
    return dict(row) if row else None


def list_subscriptions() -> list[dict]:
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM subscriptions ORDER BY id DESC")]


def delete_subscription(sid: int) -> bool:
    with _db() as con:
        return con.execute("DELETE FROM subscriptions WHERE id=?", (sid,)).rowcount > 0


def list_alerts(limit: int = 50) -> list[dict]:
    with _db() as con:
        rows = con.execute(
            "SELECT a.*, s.name, s.field_name, s.lat, s.lon FROM alerts a "
            "JOIN subscriptions s ON s.id = a.subscription_id ORDER BY a.id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


def send_email(to: str, subject: str, body: str) -> bool:
    if not (config.SMTP_HOST and to):
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
        s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
        s.send_message(msg)
    return True


def needs_alert(sub: dict, cur: dict | None) -> bool:
    return bool(cur) and cur["vci"] is not None and cur["vci"] < sub["threshold"]


def alert_message(sub: dict, cur: dict, report: dict) -> tuple[str, str]:
    """(konu, metin) döner."""
    field = sub.get("field_name") or f"{sub['lat']:.4f}, {sub['lon']:.4f}"
    message = (f"Sayın {sub['name']}, '{field}' konumundaki araziniz için {cur['t']} dönemi uydu "
               f"analizi: «{cur['class_label']}» (VCI {cur['vci']:.0f}/100, NDVI {cur['ndvi']:.2f}). "
               + " ".join(report.get("advice", [])[:1]))
    return "Kuraklık uyarısı – " + field, message


def check_all() -> dict:
    """Tüm aboneliklerin son ay durumunu kontrol eder, eşik altındakilere uyarı üretir."""
    created, checked = [], 0
    for sub in list_subscriptions():
        checked += 1
        report = service.point_report(sub["lat"], sub["lon"])
        cur = report.get("current")
        if not needs_alert(sub, cur):
            continue
        subject, message = alert_message(sub, cur, report)
        with _db() as con:
            exists = con.execute("SELECT 1 FROM alerts WHERE subscription_id=? AND period=?",
                                 (sub["id"], cur["t"])).fetchone()
        if exists:
            continue  # bu dönem için zaten uyarı gönderildi
        delivered = "site"
        try:
            if send_email(sub["email"], subject, message):
                delivered = "e-posta"
        except Exception as exc:
            log.warning("E-posta gönderilemedi (%s): %s", sub["email"], exc)
            delivered = "site (e-posta hatası)"
        with _db() as con:
            con.execute(
                "INSERT INTO alerts(subscription_id, period, ndvi, vci, level, message, delivered, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (sub["id"], cur["t"], cur["ndvi"], cur["vci"], cur["class"], message, delivered, _now()))
        created.append({"subscription_id": sub["id"], "period": cur["t"], "level": cur["class"]})
    return {"checked": checked, "new_alerts": created}
