"""
Shared mutable state — accessible across api.py and all routers.
All values reset when the server restarts.
"""
from __future__ import annotations

# Watchlist temporaire {ticker: {ticker, name, sector, added_at, is_temp}}
_TEMP_WATCHLIST: dict = {}

# Alertes killzone déclenchées aujourd'hui (dédupliquées par type+ticker)
_today_alerts: list = []

# Titres de news déjà vus pour dédupliquer les alertes
_seen_news_titles: set = set()
