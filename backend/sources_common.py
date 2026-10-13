"""Her iki veri kaynağının (GEE ve demo) ortak yardımcıları."""
from __future__ import annotations

import datetime as dt

from .config import FIRST_YEAR


def latest_month(today: dt.date | None = None) -> tuple[int, int]:
    """Tamamlanmış en son ay (aylık kompozit için ay bitmiş olmalı)."""
    today = today or dt.date.today()
    y, m = today.year, today.month - 1
    if m == 0:
        y, m = y - 1, 12
    return y, m


def month_range(end: tuple[int, int]) -> list[tuple[int, int]]:
    out = []
    y, m = FIRST_YEAR, 1
    while (y, m) <= end:
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def season_months(peak_month: int) -> list[int]:
    """Büyüme mevsimi: zirve ayı ve bir önceki/sonraki ay."""
    return [((peak_month - 2 + k) % 12) + 1 for k in range(3)]
