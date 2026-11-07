"""Google Formu yanıt tablosundan (Google Sheets) çiftçi aboneliklerini okur.

Form soruları (başlıklarda bu kelimeler geçmesi yeterli):
    "Ad Soyad", "E-posta", "Enlem", "Boylam", "Tarla adı" (isteğe bağlı),
    "Eşik" (isteğe bağlı, varsayılan 35), "Onay" (KVKK onayı, isteğe bağlı)

Tablo, Earth Engine servis hesabının e-posta adresiyle "Görüntüleyen" olarak
paylaşılmalıdır; tablo herkese açık yapılmaz (kişisel veri).
"""
from __future__ import annotations

import re

COLUMNS = {
    "email": ("posta", "mail"),
    "lat": ("enlem", "latitude"),
    "lon": ("boylam", "longitude"),
    "threshold": ("eşik", "esik", "threshold"),
    "field_name": ("tarla",),
    "consent": ("onay", "kvkk", "izin"),
}


def _num(text) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(text or ""))
    return float(m.group().replace(",", ".")) if m else None


def parse_rows(rows: list[list[str]]) -> list[dict]:
    """İlk satır başlık; geçerli konumu olan satırları abonelik olarak döner."""
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    idx = {}
    for key, words in COLUMNS.items():
        idx[key] = next((i for i, h in enumerate(header) if any(w in h for w in words)), None)
    # "Ad Soyad": "ad" geçen ama tarla adı olmayan sütun
    idx["name"] = next((i for i, h in enumerate(header)
                        if re.search(r"\bad\b|isim|ad soyad", h) and "tarla" not in h), None)

    def cell(row, key):
        i = idx.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    subs = []
    for row in rows[1:]:
        lat, lon = _num(cell(row, "lat")), _num(cell(row, "lon"))
        if lat is None or lon is None or not (35 <= lat <= 43 and 25 <= lon <= 45):
            continue
        if idx["consent"] is not None and not cell(row, "consent"):
            continue  # onay vermemiş
        thr = _num(cell(row, "threshold"))
        subs.append({
            "name": cell(row, "name") or "Çiftçi",
            "email": cell(row, "email") or None,
            "lat": lat, "lon": lon,
            "field_name": cell(row, "field_name") or None,
            "threshold": max(5.0, min(80.0, thr)) if thr is not None else 35.0,
        })
    return subs


def read_subscribers(sheet_id: str, key_file: str) -> list[dict]:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        key_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    res = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range="A1:Z5000").execute()
    return parse_rows(res.get("values", []))
