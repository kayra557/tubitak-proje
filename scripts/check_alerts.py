"""Tüm abone tarlaları uydu verisiyle kontrol eder ve gerekirse uyarı gönderir.

Her ayın başında otomatik çalıştırmak için (Linux cron örneği):
    0 8 3 * *  cd /proje/yolu && python -m scripts.check_alerts
"""
import json

from backend import alerts

if __name__ == "__main__":
    print(json.dumps(alerts.check_all(), ensure_ascii=False, indent=2))
