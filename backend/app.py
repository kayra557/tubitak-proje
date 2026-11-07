"""Flask web sunucusu: API + statik site.

Çalıştırma:  python -m backend.app   →  http://localhost:5000
"""
from __future__ import annotations

import json
import logging
import os

from flask import Flask, Response, jsonify, request, send_from_directory

from . import alerts, places, service
from .config import FIRST_YEAR, REGIONS, ROOT

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = Flask(__name__, static_folder=str(ROOT / "frontend" / "static"), static_url_path="/static")


class BadRequest(Exception):
    pass


@app.errorhandler(BadRequest)
def _bad_request(exc):
    return jsonify({"error": str(exc)}), 400


def _region_arg():
    rid = request.args.get("region", "konya")
    if rid not in REGIONS:
        raise BadRequest("Bilinmeyen bölge")
    return rid


def _period_args():
    ly, lm = service.source().latest()
    try:
        year = int(request.args.get("year", ly))
        month = int(request.args.get("month", lm))
    except ValueError:
        raise BadRequest("Yıl/ay sayı olmalı")
    if not (1 <= month <= 12) or (year, month) > (ly, lm) or year < FIRST_YEAR:
        raise BadRequest(f"Dönem {FIRST_YEAR}-01 ile {ly}-{lm:02d} arasında olmalı")
    return year, month


def _latlon(src):
    try:
        lat, lon = float(src.get("lat")), float(src.get("lon"))
    except (TypeError, ValueError):
        raise BadRequest("Geçerli enlem/boylam gerekli")
    # Türkiye ve yakın çevresi
    if not (35 <= lat <= 43 and 25 <= lon <= 45):
        raise BadRequest("Konum Türkiye sınırları dışında")
    return round(lat, 5), round(lon, 5)


@app.get("/")
def index():
    return send_from_directory(ROOT / "frontend", "index.html")


@app.get("/api/status")
def api_status():
    return jsonify(service.status())


@app.get("/api/regions")
def api_regions():
    return jsonify(service.regions())


@app.get("/api/places")
def api_places():
    return jsonify(places.as_json())


@app.get("/api/map")
def api_map():
    year, month = _period_args()
    return jsonify(service.region_map(_region_arg(), year, month))


@app.get("/api/timeseries")
def api_timeseries():
    return jsonify(service.region_timeseries(_region_arg()))


@app.get("/api/drought-history")
def api_drought_history():
    try:
        month = int(request.args.get("month", service.source().latest()[1]))
    except ValueError:
        raise BadRequest("Ay sayı olmalı")
    if not 1 <= month <= 12:
        raise BadRequest("Ay 1-12 arasında olmalı")
    return jsonify(service.drought_history(_region_arg(), month))


@app.get("/api/point")
def api_point():
    lat, lon = _latlon(request.args)
    return jsonify(service.point_report(lat, lon))


@app.get("/api/export.geojson")
def api_export():
    """Haritadaki ızgarayı QGIS'te açılabilir GeoJSON olarak indirir."""
    rid = _region_arg()
    year, month = _period_args()
    data = service.region_map(rid, year, month)
    data.pop("tiles", None)
    data.pop("summary", None)
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/geo+json",
                    headers={"Content-Disposition": f"attachment; filename={rid}_{year}_{month:02d}_kuraklik.geojson"})


@app.get("/api/subscriptions")
def api_subscriptions():
    subs = alerts.list_subscriptions()
    # Kişisel veriyi herkese açık listede maskele
    for s in subs:
        if s.get("email"):
            user, _, dom = s["email"].partition("@")
            s["email"] = (user[:2] + "***@" + dom) if dom else "***"
    return jsonify(subs)


@app.post("/api/subscriptions")
def api_subscribe():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip() or None
    if not name or len(name) > 80:
        raise BadRequest("Ad Soyad gerekli")
    if email and ("@" not in email or len(email) > 120):
        raise BadRequest("Geçerli bir e-posta girin")
    lat, lon = _latlon(body)
    try:
        threshold = float(body.get("threshold", 35))
    except (TypeError, ValueError):
        raise BadRequest("Eşik sayı olmalı")
    threshold = max(5.0, min(80.0, threshold))
    field = (body.get("field_name") or "").strip()[:80] or None
    return jsonify(alerts.add_subscription(name, email, lat, lon, field, threshold)), 201


@app.delete("/api/subscriptions/<int:sid>")
def api_unsubscribe(sid):
    return jsonify({"deleted": alerts.delete_subscription(sid)})


@app.get("/api/alerts")
def api_alerts():
    return jsonify(alerts.list_alerts())


@app.post("/api/alerts/check")
def api_check_alerts():
    return jsonify(alerts.check_all())


def main():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()
