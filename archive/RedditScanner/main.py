"""
Reddit Premarket Scanner — PRO v4
Upgrades:
✅ Time-decay + engagement weighting (from v3)
✅ Deduplication (avoid counting reposts / same title)
✅ Snapshots (daily history): saves dated copies of outputs

Outputs (current):
- reddit_signals_summary.csv
- reddit_watchlist.csv
- reddit_watchlist_swing.csv
- reddit_watchlist_pump.csv
- reddit_sentiment_signals.json
- premarket_tickers.txt

Optional snapshots (history):
- snapshots/YYYY-MM-DD/<tag>/... copies of the above

Recommended premarket run:
python main.py --refresh --cache-ttl 1800 --prefer-new --snapshot --snapshot-tag premarket
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import requests
from bs4 import BeautifulSoup
from collections import Counter, defaultdict


# -----------------------------
# Config
# -----------------------------

SUBREDDITS: Dict[str, str] = {
    "TheRaceTo10Million": "TheRaceTo10Million",
    "StockMarket": "StockMarket",
    "Daytrading": "Daytrading",
    "RealDayTrading": "RealDayTrading",
    "insidertraders": "insidertraders",
    "InsiderTradingAlerts": "InsiderTradingAlerts",
    "wallstreetinsiders": "wallstreetinsiders",
    "ValueInvesting": "ValueInvesting",
    "investing": "investing",
    "stocks": "stocks",
    "buzztickr"    : "buzztickr",
    "buzztickers"  : "buzztickers",
    "pennystocks"  : "pennystocks",
    "10xPennyStocks": "10xPennyStocks",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}

POST_LIMIT = 50
TOP_N_ANALYZE = 30
MAX_RETRIES = 3
SLEEP_BETWEEN_SUBS = 1.2

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

FOCUS_TICKERS = ["NVDA", "TSLA", "PLTR", "SMCI", "AMD", "GME", "AMC", "BBAI", "NVTS"]

SENTIMENT_KEYWORDS = {
    "bullish": [
        "buy", "bull", "long", "upside", "breakout", "rip", "runner", "gap up",
        "calls", "call", "strong", "beat", "guidance raised", "reversal",
        "moon", "rocket", "to the moon", "pt", "price target", "buying", "loading up",
        "squeeze", "short squeeze", "gamma", "gamma squeeze",
        "🚀", "💎", "🟢",
    ],
    "bearish": [
        "sell", "bear", "short", "downside", "dump", "rug", "crash", "selloff",
        "puts", "put", "overvalued", "miss", "gap down", "dilution", "offering",
        "bagholder", "rekt", "🟥", "🔻",
    ],
    "insider_buy": [
        "form4", "form 4", "13f", "13d", "13g", "schedule 13d", "sec filing",
        "insider", "insiders buying", "open market", "purchase", "bought",
        "accumulating", "added shares", "increased stake", "stake up",
        "whale", "institution", "institutional", "filed", "disclosed",
        "ceo buy", "cfo buy", "director buy", "exec buy", "executive buy",
        "chairman buy", "10b5-1", "10b5 1",
    ],
}

HYPE_WORDS = [
    "squeeze", "short squeeze", "gamma", "gamma squeeze",
    "moon", "to the moon", "rocket", "yolo", "ape",
    "send it", "rip", "runner", "parabolic", "halt", "halts",
    "pump", "pumping",
    "🚀", "💎", "🟢",
]

TICKER_RE = re.compile(r"\b\$?[A-Z]{2,5}\b")
TICKER_STOP = {
    "CEO", "CFO", "SEC", "USA", "USD", "EUR", "ETF", "EPS", "IPO", "ATH", "AI", "EV",
    "DD", "WSB", "FOMO", "IMO", "TLDR", "FYI", "OTC",
    "BUY", "SELL", "LONG", "SHORT", "BULL", "BEAR", "CALL", "CALLS", "PUT", "PUTS",
    "MOON", "ROCKET", "SQUEEZE", "GAMMA", "HOLD", "HODL", "PUMP", "DUMP",
    "ALERT", "ALERTS", "TARGET", "PT", "NEWS", "UPDATE",
}


OUTPUT_FILES = [
    "reddit_signals_summary.csv",
    "reddit_watchlist.csv",
    "reddit_watchlist_swing.csv",
    "reddit_watchlist_pump.csv",
    "reddit_sentiment_signals.json",
    "premarket_tickers.txt",
]


# -----------------------------
# Models
# -----------------------------

@dataclass
class PostSignal:
    title: str
    signal: str
    confidence: int
    tickers: List[str]
    score: Dict[str, int]
    hype_score: int
    permalink: str = ""
    author: str = ""
    score_upvotes: Optional[int] = None
    num_comments: Optional[int] = None
    created_utc: Optional[float] = None
    weight_time: float = 1.0
    weight_eng: float = 1.0
    weight_total: float = 1.0
    title_key: str = ""


# -----------------------------
# Cache
# -----------------------------

def cache_path(sub: str) -> Path:
    return CACHE_DIR / f"{sub}.json"

def load_cache(sub: str, ttl_sec: int) -> Optional[List[dict]]:
    p = cache_path(sub)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > ttl_sec:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_cache(sub: str, posts: List[dict]) -> None:
    cache_path(sub).write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")


# -----------------------------
# Strict Rate Limiter
# -----------------------------

_last_request = 0.0
_rl_lock = threading.Lock()

def _rate_limit(min_interval: float = 1.0) -> None:
    global _last_request
    with _rl_lock:
        now = time.time()
        dt = now - _last_request
        if dt < min_interval:
            time.sleep(min_interval - dt)
        time.sleep(random.uniform(0.02, 0.08))
        _last_request = time.time()


# -----------------------------
# HTTP helpers
# -----------------------------

_session = requests.Session()
_session.headers.update(HEADERS)

def _parse_retry_after_seconds(r: requests.Response) -> Optional[float]:
    ra = r.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)
    except Exception:
        return None

def _get(url: str) -> Optional[requests.Response]:
    backoff = 0.8
    for attempt in range(MAX_RETRIES):
        _rate_limit(1.0)
        try:
            r = _session.get(url, timeout=20)

            if r.status_code == 429:
                ra = _parse_retry_after_seconds(r)
                sleep_s = ra if ra is not None else backoff * (attempt + 1)
                time.sleep(min(10.0, max(1.0, sleep_s)))
                continue

            if r.status_code in (401, 403):
                return r

            r.raise_for_status()
            return r

        except requests.RequestException:
            time.sleep(min(10.0, backoff * (attempt + 1)))
            continue

    return None


# -----------------------------
# Fetchers
# -----------------------------

def fetch_posts_json(sub: str, limit: int, prefer_new: bool) -> List[dict]:
    urls = [
        f"https://www.reddit.com/r/{sub}/new.json?limit={limit}&raw_json=1",
        f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}&raw_json=1",
        f"https://www.reddit.com/r/{sub}/.json?limit={limit}&raw_json=1",
    ] if prefer_new else [
        f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}&raw_json=1",
        f"https://www.reddit.com/r/{sub}/new.json?limit={limit}&raw_json=1",
        f"https://www.reddit.com/r/{sub}/.json?limit={limit}&raw_json=1",
    ]

    for url in urls:
        r = _get(url)
        if not r or r.status_code in (401, 403, 429):
            continue
        try:
            data = r.json()
            children = data.get("data", {}).get("children", [])
            posts: List[dict] = []
            for ch in children:
                d = ch.get("data", {})
                title = d.get("title", "")
                if not isinstance(title, str) or len(title.strip()) <= 5:
                    continue
                posts.append({
                    "title": title.strip(),
                    "permalink": d.get("permalink", ""),
                    "author": d.get("author", ""),
                    "score": d.get("score", None),
                    "num_comments": d.get("num_comments", None),
                    "created_utc": d.get("created_utc", None),
                })
            if posts:
                src = "new" if "new.json" in url else ("hot" if "hot.json" in url else "listing")
                print(f"✅ {sub}: {len(posts)} posts (JSON:{src})")
                return posts
        except Exception:
            continue
    return []

def fetch_posts_old_reddit(sub: str, limit: int) -> List[dict]:
    url = f"https://old.reddit.com/r/{sub}/"
    r = _get(url)
    if not r or r.status_code in (401, 403, 429):
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out: List[dict] = []
    for a in soup.select("a.title")[:limit]:
        t = a.get_text(strip=True)
        if t and len(t) > 5:
            out.append({"title": t, "permalink": "", "author": "", "score": None, "num_comments": None, "created_utc": None})
    if out:
        print(f"✅ {sub}: {len(out)} posts (old.reddit)")
    return out

def fetch_posts_playwright(sub: str, limit: int) -> List[dict]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return []

    titles: List[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://www.reddit.com/r/{sub}/", timeout=60000)
        page.wait_for_timeout(5000)

        for sel in ['[data-testid="post-title"]', "article h3", "h3"]:
            try:
                page.wait_for_selector(sel, timeout=5000)
                titles = [t.strip() for t in page.locator(sel).all_text_contents() if isinstance(t, str)]
                titles = [t for t in titles if len(t) > 5]
                if titles:
                    break
            except Exception:
                continue

        browser.close()

    if titles:
        print(f"✅ {sub}: {len(titles[:limit])} posts (Playwright)")
    return [{"title": t, "permalink": "", "author": "", "score": None, "num_comments": None, "created_utc": None} for t in titles[:limit]]

def fetch_posts(sub: str, limit: int, ttl_sec: int, refresh: bool, prefer_new: bool) -> List[dict]:
    if not refresh:
        cached = load_cache(sub, ttl_sec)
        if cached:
            print(f"🧠 {sub}: cache hit ({len(cached)} posts)")
            return cached

    posts = fetch_posts_json(sub, limit, prefer_new=prefer_new)
    if not posts:
        posts = fetch_posts_old_reddit(sub, min(30, limit))
    if not posts:
        posts = fetch_posts_playwright(sub, min(30, limit))

    if posts:
        save_cache(sub, posts)
    return posts


# -----------------------------
# Optional whitelist
# -----------------------------

def load_symbols_whitelist(path: Optional[str]) -> Optional[Set[str]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        print(f"ℹ️ Symbols whitelist not found: {path} (skipping)")
        return None
    try:
        df = pd.read_csv(p)
        if "Symbol" in df.columns:
            syms = set(df["Symbol"].astype(str).str.upper().str.strip().tolist())
        else:
            syms = set(df.iloc[:, 0].astype(str).str.upper().str.strip().tolist())
        syms = {s for s in syms if s.isalpha() and 1 < len(s) <= 5}
        print(f"✅ Loaded symbols whitelist: {len(syms)} symbols")
        return syms
    except Exception as e:
        print(f"⚠️ Failed to load symbols whitelist: {e}")
        return None


# -----------------------------
# PRO: Dedup
# -----------------------------

_nonword = re.compile(r"[^a-z0-9]+")

def title_dedup_key(title: str) -> str:
    """
    Normalize title so minor punctuation/spacing differences become the same.
    Also removes $TICKER style tokens so crossposts don't explode counts.
    """
    t = title.lower()
    t = re.sub(r"\$[a-z]{1,5}\b", "", t)
    t = _nonword.sub(" ", t)
    t = " ".join(t.split())
    return t.strip()


# -----------------------------
# Scoring (time + engagement)
# -----------------------------

def calc_time_weight(created_utc: Optional[float], now_ts: float, half_life_hours: float = 6.0, min_w: float = 0.2) -> float:
    if not created_utc:
        return 1.0
    age_hours = max(0.0, (now_ts - float(created_utc)) / 3600.0)
    w = math.exp(-math.log(2.0) * age_hours / max(0.001, half_life_hours))
    return max(min_w, float(w))

def calc_engagement_weight(upvotes: Optional[int], comments: Optional[int], max_w: float = 6.0) -> float:
    up = max(0, int(upvotes or 0))
    com = max(0, int(comments or 0))
    w = 1.0 + math.log10(1 + up) + 0.5 * math.log10(1 + com)
    return float(min(max_w, w))

def hype_score(text_lower: str) -> int:
    return sum(1 for w in HYPE_WORDS if w in text_lower)

def extract_tickers(title: str, whitelist: Optional[Set[str]] = None) -> List[str]:
    out: List[str] = []
    for m in TICKER_RE.finditer(title):
        raw = m.group(0)
        had_dollar = raw.startswith("$")
        t = raw.upper().replace("$", "")

        if not t.isalpha():
            continue
        if not (2 <= len(t) <= 5):
            continue
        if len(t) == 2 and not had_dollar:
            continue
        if t in TICKER_STOP:
            continue
        if whitelist is not None and t not in whitelist:
            continue

        out.append(t)

    seen = set()
    dedup = []
    for t in out:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup

def net_stability_bonus(net: float) -> float:
    return max(0.0, 20.0 - abs(net - 12.0) * 2.0)

def swing_score(net: float, insider: float, hype: float) -> int:
    score = 3.0 * insider + net_stability_bonus(net) - 1.0 * hype
    return max(0, int(round(score)))

def pump_score(net: float, insider: float, hype: float) -> int:
    score = 3.0 * hype + 2.0 * max(0.0, net) - 2.0 * insider
    return max(0, int(round(score)))

def label_trade_style(swing: int, pump: int) -> str:
    if swing >= 12 and swing > pump * 1.2:
        return "SWING"
    if pump >= 12 and pump > swing * 1.2:
        return "PUMP_RISK"
    return "MIXED"

def rationale_tag(net: float, insider: float, hype: float, swing: int, pump: int) -> str:
    if swing >= 20 and insider >= 2 and hype <= 6:
        return "Insider-driven / low hype"
    if swing >= 18 and insider >= 1 and 6 < hype <= 14:
        return "Insiders + community aligned"
    if pump >= 25 and insider <= 1 and hype >= 10:
        return "Pure hype / rug risk"
    if net < -5:
        return "Bearish pressure"
    if hype >= 15:
        return "Very high hype"
    return "Mixed / needs chart confirmation"

def analyze_post(
    p: dict,
    now_ts: float,
    half_life_hours: float,
    whitelist: Optional[Set[str]],
    dedup_key: str,
) -> Optional[PostSignal]:
    title = p.get("title", "")
    if not isinstance(title, str) or len(title.strip()) <= 5:
        return None

    tl = title.lower()
    score = {
        "bullish": sum(1 for w in SENTIMENT_KEYWORDS["bullish"] if w in tl),
        "bearish": sum(1 for w in SENTIMENT_KEYWORDS["bearish"] if w in tl),
        "insider_buy": sum(1 for w in SENTIMENT_KEYWORDS["insider_buy"] if w in tl),
    }
    total = sum(score.values())
    if total == 0:
        return None

    permalink = p.get("permalink") or ""
    if permalink and not permalink.startswith("http"):
        permalink = "https://www.reddit.com" + permalink

    created_utc = p.get("created_utc", None)
    up = p.get("score", None)
    com = p.get("num_comments", None)

    w_time = calc_time_weight(created_utc, now_ts, half_life_hours=half_life_hours, min_w=0.2)
    w_eng = calc_engagement_weight(up, com, max_w=6.0)
    w_total = w_time * w_eng

    return PostSignal(
        title=title[:180],
        signal=max(score, key=score.get),
        confidence=total,
        tickers=extract_tickers(title, whitelist=whitelist),
        score=score,
        hype_score=hype_score(tl),
        permalink=permalink,
        author=p.get("author", "") or "",
        score_upvotes=up,
        num_comments=com,
        created_utc=created_utc,
        weight_time=w_time,
        weight_eng=w_eng,
        weight_total=w_total,
        title_key=dedup_key,
    )


# -----------------------------
# Snapshots
# -----------------------------

def save_snapshot(snapshot_dir: str, tag: str) -> Optional[Path]:
    """
    Copies current outputs into snapshots/YYYY-MM-DD/<tag>/
    """
    day = datetime.now().strftime("%Y-%m-%d")
    safe_tag = re.sub(r"[^a-zA-Z0-9_-]+", "_", tag.strip() or "snapshot")
    dest = Path(snapshot_dir) / day / safe_tag
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    for f in OUTPUT_FILES:
        src = Path(f)
        if src.exists():
            (dest / src.name).write_bytes(src.read_bytes())
            copied += 1

    # small metadata
    meta = {
        "date": day,
        "tag": safe_tag,
        "copied_files": copied,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dest if copied > 0 else None


# -----------------------------
# Pipeline
# -----------------------------

def run(
    refresh: bool,
    ttl_sec: int,
    focus_mode: bool,
    prefer_new: bool,
    half_life_hours: float,
    whitelist: Optional[Set[str]],
    dedup: bool,
) -> List[dict]:
    now_ts = time.time()
    all_data: List[dict] = []

    for label, sub in SUBREDDITS.items():
        print(f"🔍 Scraping {label}")
        posts = fetch_posts(sub, POST_LIMIT, ttl_sec, refresh, prefer_new=prefer_new)

        # Weighted summaries
        summary_w = {"bullish": 0.0, "bearish": 0.0, "insider_buy": 0.0}
        hype_total_w = 0.0

        tickers_raw = Counter()
        ticker_stats = defaultdict(lambda: {
            "mentions": 0,
            "weight_sum": 0.0,
            "bull_w": 0.0,
            "bear_w": 0.0,
            "ins_w": 0.0,
            "hype_w": 0.0,
        })

        out_posts: List[dict] = []
        seen_keys: Set[str] = set()
        duplicates_skipped = 0

        for p in posts[:TOP_N_ANALYZE]:
            key = title_dedup_key(p.get("title", "") or "")
            if dedup and key and key in seen_keys:
                duplicates_skipped += 1
                continue
            if dedup and key:
                seen_keys.add(key)

            ps = analyze_post(
                p,
                now_ts=now_ts,
                half_life_hours=half_life_hours,
                whitelist=whitelist,
                dedup_key=key,
            )
            if not ps:
                continue

            out_posts.append({
                "title": ps.title,
                "signal": ps.signal,
                "confidence": ps.confidence,
                "tickers": ps.tickers,
                "score": ps.score,
                "hype_score": ps.hype_score,
                "permalink": ps.permalink,
                "author": ps.author,
                "score_upvotes": ps.score_upvotes,
                "num_comments": ps.num_comments,
                "created_utc": ps.created_utc,
                "weight_time": round(ps.weight_time, 4),
                "weight_eng": round(ps.weight_eng, 4),
                "weight_total": round(ps.weight_total, 4),
                "title_key": ps.title_key,
            })

            w = ps.weight_total
            summary_w["bullish"] += ps.score["bullish"] * w
            summary_w["bearish"] += ps.score["bearish"] * w
            summary_w["insider_buy"] += ps.score["insider_buy"] * w
            hype_total_w += ps.hype_score * w

            tickers_raw.update(ps.tickers)
            for t in ps.tickers:
                ts = ticker_stats[t]
                ts["mentions"] += 1
                ts["weight_sum"] += w
                ts["bull_w"] += ps.score["bullish"] * w
                ts["bear_w"] += ps.score["bearish"] * w
                ts["ins_w"] += ps.score["insider_buy"] * w
                ts["hype_w"] += ps.hype_score * w

        if focus_mode:
            focus_set = set(FOCUS_TICKERS)
            tickers_raw = Counter({t: c for t, c in tickers_raw.items() if t in focus_set})
            ticker_stats = {t: s for t, s in ticker_stats.items() if t in focus_set}

        net_w = summary_w["bullish"] - summary_w["bearish"]
        swing = swing_score(net_w, summary_w["insider_buy"], hype_total_w)
        pump = pump_score(net_w, summary_w["insider_buy"], hype_total_w)
        style = label_trade_style(swing, pump)
        rationale = rationale_tag(net_w, summary_w["insider_buy"], hype_total_w, swing, pump)

        all_data.append({
            "subreddit": label,
            "source": sub,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "posts": out_posts,

            "sentiment_summary": {
                "bullish": int(round(summary_w["bullish"])),
                "bearish": int(round(summary_w["bearish"])),
                "insider_buy": int(round(summary_w["insider_buy"])),
            },
            "net_sentiment": int(round(net_w)),
            "hype_total": int(round(hype_total_w)),

            "swing_score": swing,
            "pump_score": pump,
            "trade_style": style,
            "rationale": rationale,

            "hot_tickers": dict(tickers_raw),
            "ticker_stats": dict(ticker_stats),

            "half_life_hours": half_life_hours,
            "dedup_enabled": dedup,
            "duplicates_skipped": duplicates_skipped,
        })

        time.sleep(SLEEP_BETWEEN_SUBS)

    return all_data


def save_outputs(
    data: List[dict],
    swing_min: int,
    pump_min: int,
    mentions_min: int,
    pump_max_for_swing: int,
    insider_min_for_swing: int,
    insider_max_for_pump: int,
) -> None:
    with open("reddit_sentiment_signals.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Summary CSV (subreddit-level)
    rows = []
    for sub in data:
        s = sub["sentiment_summary"]
        net = sub["net_sentiment"]
        top5 = Counter(sub["hot_tickers"]).most_common(5)
        top_str = ", ".join(t for t, _ in top5)

        rows.append([
            sub["subreddit"],
            s["bullish"],
            s["bearish"],
            s["insider_buy"],
            net,
            sub["hype_total"],
            sub["swing_score"],
            sub["pump_score"],
            sub["trade_style"],
            sub.get("rationale", ""),
            sub.get("duplicates_skipped", 0),
            top_str,
            sub["scraped_at"],
            len(sub["posts"]),
            sub.get("half_life_hours", 6.0),
        ])

    pd.DataFrame(rows, columns=[
        "Subreddit","Bullish","Bearish","Insider_Buy","Net_Sentiment","Hype_Total",
        "Swing_Score","Pump_Score","Trade_Style","Rationale","Duplicates_Skipped",
        "Top_Tickers","Scraped_At","Posts_Analyzed","HalfLifeHours",
    ]).to_csv("reddit_signals_summary.csv", index=False, encoding="utf-8")

    # Watchlist enriched (ticker-level)
    agg = defaultdict(lambda: {
        "mentions": 0,
        "weight_sum": 0.0,
        "bull_w": 0.0,
        "bear_w": 0.0,
        "ins_w": 0.0,
        "hype_w": 0.0,
        "subs": Counter(),
    })

    for sub in data:
        stats = sub.get("ticker_stats", {})
        sub_name = sub.get("subreddit", "")
        for t, s in stats.items():
            agg[t]["mentions"] += int(s.get("mentions", 0))
            agg[t]["weight_sum"] += float(s.get("weight_sum", 0.0))
            agg[t]["bull_w"] += float(s.get("bull_w", 0.0))
            agg[t]["bear_w"] += float(s.get("bear_w", 0.0))
            agg[t]["ins_w"] += float(s.get("ins_w", 0.0))
            agg[t]["hype_w"] += float(s.get("hype_w", 0.0))
            agg[t]["subs"][sub_name] += int(s.get("mentions", 0))

    watch_rows = []
    for t, a in agg.items():
        mentions = int(a["mentions"])
        if mentions < 1:
            continue

        net = a["bull_w"] - a["bear_w"]
        ins = a["ins_w"]
        hype = a["hype_w"]

        swing = swing_score(net, ins, hype)
        pump = pump_score(net, ins, hype)
        style = label_trade_style(swing, pump)
        rationale = rationale_tag(net, ins, hype, swing, pump)
        top_subs = ", ".join([s for s, _ in a["subs"].most_common(3)])

        watch_rows.append([
            t,
            mentions,
            round(a["weight_sum"], 2),
            int(round(net)),
            int(round(ins)),
            int(round(hype)),
            swing,
            pump,
            style,
            rationale,
            top_subs,
        ])

    wl_df = pd.DataFrame(watch_rows, columns=[
        "Ticker","Mentions","Weight_Sum","Net_Sentiment","Insider_Buy","Hype_Total",
        "Swing_Score","Pump_Score","Trade_Style","Rationale","Top_Subreddits",
    ])

    wl_df = wl_df.sort_values(["Pump_Score", "Mentions"], ascending=False)
    wl_df.to_csv("reddit_watchlist.csv", index=False, encoding="utf-8")

    swing_df = wl_df[
        (wl_df["Mentions"] >= mentions_min) &
        (wl_df["Swing_Score"] >= swing_min) &
        (wl_df["Pump_Score"] <= pump_max_for_swing) &
        (wl_df["Insider_Buy"] >= insider_min_for_swing)
    ].sort_values(["Swing_Score", "Mentions"], ascending=False)

    pump_df = wl_df[
        (wl_df["Mentions"] >= mentions_min) &
        (wl_df["Pump_Score"] >= pump_min) &
        (wl_df["Insider_Buy"] <= insider_max_for_pump)
    ].sort_values(["Pump_Score", "Mentions"], ascending=False)

    swing_df.to_csv("reddit_watchlist_swing.csv", index=False, encoding="utf-8")
    pump_df.to_csv("reddit_watchlist_pump.csv", index=False, encoding="utf-8")

    swing_tickers = swing_df["Ticker"].head(20).tolist()
    pump_tickers = pump_df["Ticker"].head(20).tolist()

    with open("premarket_tickers.txt", "w", encoding="utf-8") as f:
        f.write("SWING_TICKERS (comma):\n")
        f.write(", ".join(swing_tickers) + "\n\n")
        f.write("PUMP_TICKERS (comma):\n")
        f.write(", ".join(pump_tickers) + "\n")

    print("💾 Outputs saved.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-ttl", type=int, default=3600)
    parser.add_argument("--focus", action="store_true")
    parser.add_argument("--prefer-new", action="store_true")

    parser.add_argument("--half-life-hours", type=float, default=6.0)
    parser.add_argument("--symbols-file", type=str, default="")

    # Dedup
    parser.add_argument("--no-dedup", action="store_true", help="Disable title deduplication")

    # Snapshots
    parser.add_argument("--snapshot", action="store_true", help="Save outputs into snapshots/")
    parser.add_argument("--snapshot-dir", type=str, default="snapshots")
    parser.add_argument("--snapshot-tag", type=str, default="premarket")

    # Thresholds
    parser.add_argument("--swing-min", type=int, default=18)
    parser.add_argument("--pump-min", type=int, default=25)
    parser.add_argument("--mentions-min", type=int, default=2)
    parser.add_argument("--pump-max-for-swing", type=int, default=18)
    parser.add_argument("--insider-min-for-swing", type=int, default=1)
    parser.add_argument("--insider-max-for-pump", type=int, default=1)

    args = parser.parse_args()

    whitelist = load_symbols_whitelist(args.symbols_file) if args.symbols_file else None
    dedup = not args.no_dedup

    print("🚀 Reddit Premarket Scanner — PRO v4 (dedup + snapshots)")
    data = run(
        refresh=args.refresh,
        ttl_sec=args.cache_ttl,
        focus_mode=args.focus,
        prefer_new=args.prefer_new,
        half_life_hours=args.half_life_hours,
        whitelist=whitelist,
        dedup=dedup,
    )

    total_bull = sum(d["sentiment_summary"]["bullish"] for d in data)
    total_bear = sum(d["sentiment_summary"]["bearish"] for d in data)
    total_ins = sum(d["sentiment_summary"]["insider_buy"] for d in data)

    print("\n📈 Global summary (weighted):")
    print(f"🐂 Bullish: {total_bull}")
    print(f"🐻 Bearish: {total_bear}")
    print(f"👤 Insider: {total_ins}")
    print(f"📊 Net: {total_bull - total_bear:+d}")

    save_outputs(
        data,
        swing_min=args.swing_min,
        pump_min=args.pump_min,
        mentions_min=args.mentions_min,
        pump_max_for_swing=args.pump_max_for_swing,
        insider_min_for_swing=args.insider_min_for_swing,
        insider_max_for_pump=args.insider_max_for_pump,
    )

    if args.snapshot:
        dest = save_snapshot(args.snapshot_dir, args.snapshot_tag)
        if dest:
            print(f"📦 Snapshot saved: {dest}")
        else:
            print("⚠️ Snapshot not saved (no outputs found).")


if __name__ == "__main__":
    main()
