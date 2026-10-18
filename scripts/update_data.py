"""Google Earth Engine'den eksik ayların ızgara NDVI değerlerini çekip data/store'a yazar.

İlk çalıştırmada 2017'den bugüne tüm aylar çekilir (uzun sürer, birkaç
çalıştırmaya bölünebilir). Sonraki çalıştırmalarda yalnızca yeni ay ve geç gelen
görüntüler için son birkaç ay yenilenir.

    python -m scripts.update_data                    # tüm bölgeler
    python -m scripts.update_data --max-minutes 60   # en fazla 1 saat çalış, kalanı sonraki sefere
"""
import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend import analysis, store
from backend.config import REGIONS
from backend.sources_common import latest_month, month_range

log = logging.getLogger("update_data")


def _with_retry(fn, *args, tries=3):
    for attempt in range(1, tries + 1):
        try:
            return fn(*args)
        except Exception as exc:  # GEE zaman aşımı / kota hataları geçici olabilir
            if attempt == tries:
                raise
            wait = 30 * attempt
            log.warning("Hata (%s), %d sn sonra tekrar denenecek: %s", args[:3], wait, exc)
            time.sleep(wait)


def prepare_store(src, rid: str) -> dict:
    st = store.load(rid)
    if st and store.is_current(st, rid) and st["source"] == "gee":
        return st
    log.info("[%s] Yeni depo oluşturuluyor: hücreler ve tarım alanı oranları hesaplanıyor…", rid)
    cells = analysis.grid_cells(REGIONS[rid]["polygon"])
    crops = _with_retry(src.crop_fractions, rid, cells)
    for c, f in zip(cells, crops):
        c["crop"] = f or 0.0
    st = store.new_store(rid, "gee", cells)
    store.save(st)
    return st


def months_to_fetch(st: dict, refresh: int) -> list[str]:
    wanted = [f"{y}-{m:02d}" for y, m in month_range(latest_month())]
    missing = [k for k in reversed(wanted) if k not in st["months"]]  # en yeniden eskiye
    have = sorted(k for k in st["months"] if k in wanted)
    return missing + [k for k in have[-refresh:] if k not in missing] if refresh else missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="*", default=list(REGIONS))
    ap.add_argument("--max-minutes", type=float, default=300)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--refresh", type=int, default=2, help="geç gelen görüntüler için yenilenecek son ay sayısı")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    from backend.gee_source import GEESource

    src = GEESource()
    deadline = time.monotonic() + a.max_minutes * 60
    stores = {rid: prepare_store(src, rid) for rid in a.regions}
    # Bölgeleri birlikte ilerlet (en yeni aydan eskiye): süre biterse her bölgede güncel aylar hazır olur
    todo = sorted(((key, rid) for rid, st in stores.items() for key in months_to_fetch(st, a.refresh)),
                  key=lambda t: t[0], reverse=True)
    log.info("%d (bölge, ay) çekilecek", len(todo))
    done = skipped = 0

    def fetch(key, rid):
        if time.monotonic() > deadline:
            return None
        y, m = map(int, key.split("-"))
        return _with_retry(src.grid_month, rid, y, m, stores[rid]["cells"])

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futures = {ex.submit(fetch, key, rid): (key, rid) for key, rid in todo}
        for fut in as_completed(futures):
            key, rid = futures[fut]
            try:
                values = fut.result()
            except Exception as exc:
                log.error("[%s] %s alınamadı, sonraki çalıştırmada tekrar denenecek: %s", rid, key, exc)
                skipped += 1
                continue
            if values is None:
                skipped += 1  # süre doldu
                continue
            store.set_month(stores[rid], key, values)
            store.save(stores[rid])  # her aydan sonra kaydet: iş yarıda kesilse de emek kaybolmaz
            done += 1
            log.info("[%s] %s tamam (%d hücrede veri)", rid, key, sum(v is not None for v in values))

    log.info("Bitti: %d ay kaydedildi, %d ay sonraya kaldı.", done, skipped)


if __name__ == "__main__":
    main()
