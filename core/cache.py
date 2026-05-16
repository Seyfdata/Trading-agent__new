"""
Cache TTL centralisé — dictionnaire en mémoire avec expiration par clé.

Usage :
    from core.cache import cache_get, cache_set, cache_clear

    data = cache_get("indicators_NVDA")
    if data is None:
        data = compute_expensive_thing()
        cache_set("indicators_NVDA", data, ttl_seconds=300)
"""

from __future__ import annotations
import time

_STORE: dict = {}


def cache_get(key: str):
    """Retourne la valeur en cache si non expirée, sinon None."""
    entry = _STORE.get(key)
    if entry and time.time() < entry["expires"]:
        return entry["data"]
    return None


def cache_set(key: str, data, ttl_seconds: int = 300) -> None:
    """Stocke data sous key pour ttl_seconds secondes."""
    _STORE[key] = {"data": data, "expires": time.time() + ttl_seconds}


def cache_clear(key: str | None = None) -> None:
    """Vide le cache : une clé si key fourni, tout le cache sinon."""
    if key is None:
        _STORE.clear()
    else:
        _STORE.pop(key, None)
