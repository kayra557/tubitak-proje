"""Havzalardaki il ve ilçe merkezleri (haritada etiket ve "en yakın yerleşim" için).

Koordinatlar yaklaşık merkez noktalarıdır: [ad, il, enlem, boylam, tür]
"""
from __future__ import annotations

import math

PLACES = [
    # --- Konya Kapalı Havzası ---
    ("Konya", "Konya", 37.871, 32.485, "il"),
    ("Aksaray", "Aksaray", 38.370, 34.030, "il"),
    ("Karaman", "Karaman", 37.181, 33.215, "il"),
    ("Niğde", "Niğde", 37.966, 34.679, "il"),
    ("Çumra", "Konya", 37.573, 32.774, "ilce"),
    ("Karapınar", "Konya", 37.716, 33.551, "ilce"),
    ("Ereğli", "Konya", 37.513, 34.047, "ilce"),
    ("Cihanbeyli", "Konya", 38.658, 32.924, "ilce"),
    ("Kulu", "Konya", 39.094, 33.081, "ilce"),
    ("Beyşehir", "Konya", 37.677, 31.725, "ilce"),
    ("Seydişehir", "Konya", 37.419, 31.849, "ilce"),
    ("Ilgın", "Konya", 38.279, 31.914, "ilce"),
    ("Kadınhanı", "Konya", 38.240, 32.211, "ilce"),
    ("Sarayönü", "Konya", 38.263, 32.406, "ilce"),
    ("Altınekin", "Konya", 38.308, 32.869, "ilce"),
    ("Emirgazi", "Konya", 37.902, 33.837, "ilce"),
    ("Eskil", "Aksaray", 38.401, 33.413, "ilce"),
    ("Sultanhanı", "Aksaray", 38.248, 33.547, "ilce"),
    ("Bor", "Niğde", 37.890, 34.559, "ilce"),
    # --- Gediz Havzası ---
    ("Manisa", "Manisa", 38.612, 27.426, "il"),
    ("Uşak", "Uşak", 38.682, 29.408, "il"),
    ("Salihli", "Manisa", 38.483, 28.140, "ilce"),
    ("Alaşehir", "Manisa", 38.350, 28.517, "ilce"),
    ("Turgutlu", "Manisa", 38.495, 27.700, "ilce"),
    ("Akhisar", "Manisa", 38.918, 27.840, "ilce"),
    ("Kula", "Manisa", 38.547, 28.650, "ilce"),
    ("Demirci", "Manisa", 39.046, 28.659, "ilce"),
    ("Simav", "Kütahya", 39.088, 28.979, "ilce"),
    ("Gediz", "Kütahya", 39.004, 29.411, "ilce"),
    ("Menemen", "İzmir", 38.607, 27.069, "ilce"),
    # --- Büyük Menderes Havzası ---
    ("Aydın", "Aydın", 37.845, 27.845, "il"),
    ("Denizli", "Denizli", 37.776, 29.086, "il"),
    ("Nazilli", "Aydın", 37.913, 28.321, "ilce"),
    ("Söke", "Aydın", 37.749, 27.406, "ilce"),
    ("Çine", "Aydın", 37.612, 28.061, "ilce"),
    ("Kuyucak", "Aydın", 37.913, 28.459, "ilce"),
    ("Sarayköy", "Denizli", 37.923, 28.925, "ilce"),
    ("Çivril", "Denizli", 38.301, 29.739, "ilce"),
    ("Dinar", "Afyonkarahisar", 38.065, 30.165, "ilce"),
]


def as_json() -> list[dict]:
    return [{"name": n, "province": p, "lat": la, "lon": lo, "type": t} for n, p, la, lo, t in PLACES]


def nearest(lat: float, lon: float) -> dict:
    """En yakın il/ilçe merkezi ve kuş uçuşu uzaklığı (km)."""
    def km(la, lo):
        dx = (lo - lon) * 111.32 * math.cos(math.radians(lat))
        dy = (la - lat) * 110.57
        return math.hypot(dx, dy)

    n, p, la, lo, t = min(PLACES, key=lambda r: km(r[2], r[3]))
    return {"name": n, "province": p, "type": t, "distance_km": round(km(la, lo), 1)}
