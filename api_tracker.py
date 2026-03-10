"""In-memory API usage tracker with daily counters.

Resets on server restart. Thread-safe via threading.Lock.
"""

import threading
from datetime import date

_lock = threading.Lock()
_counters = {}  # {service: count}
_today = date.today()

# Daily limits per service (0 = unlimited)
LIMITS = {
    "gemini_flash_lite": 1500,
    "gemini_flash": 1500,
    "gemini_pro": 50,
    "alpha_vantage": 25,
    "newsapi": 100,
    "yahoo_chart": 0,
    "yahoo_news": 0,
    "finviz": 0,
    "finviz_news": 0,
    "google_news": 0,
}

LABELS = {
    "gemini_flash_lite": "Gemini Flash-Lite",
    "gemini_flash": "Gemini Flash",
    "gemini_pro": "Gemini Pro",
    "alpha_vantage": "Alpha Vantage",
    "newsapi": "NewsAPI",
    "yahoo_chart": "Yahoo Chart",
    "yahoo_news": "Yahoo News RSS",
    "finviz": "Finviz (Data)",
    "finviz_news": "Finviz (News)",
    "google_news": "Google News RSS",
}


def _reset_if_new_day():
    """Reset counters if the date has changed."""
    global _today, _counters
    today = date.today()
    if today != _today:
        _counters = {}
        _today = today


def track(service):
    """Increment the counter for a service."""
    with _lock:
        _reset_if_new_day()
        _counters[service] = _counters.get(service, 0) + 1


def get_usage():
    """Return usage data for all tracked services."""
    with _lock:
        _reset_if_new_day()
        result = []
        for service in LIMITS:
            count = _counters.get(service, 0)
            limit = LIMITS[service]
            pct = round(count / limit * 100, 1) if limit > 0 else 0
            result.append({
                "service": service,
                "label": LABELS.get(service, service),
                "used": count,
                "limit": limit,
                "pct": pct,
            })
        return {"date": str(_today), "services": result}
