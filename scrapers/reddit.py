"""
Module Reddit — Wrapper pour le RedditScanner PRO v4.

Ce module lance ton scanner existant (RedditScanner/main.py),
lit les CSV/JSON qu'il produit, et formate les résultats
pour le morning scan.

PAS BESOIN de l'API Reddit ni de PRAW.
Ton scanner utilise le JSON public de Reddit.

Prérequis :
  pip install pandas requests beautifulsoup4
  Le dossier RedditScanner/ doit être dans trading-agent/
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from config.settings import WATCHLIST, EMOJI_FIRE, EMOJI_BULL, EMOJI_BEAR, EMOJI_NEUTRAL


# ── Liste de référence — S&P 500 + Nasdaq 100 + watchlist perso ──────────────
# Tout ticker ABSENT de cette liste sera marqué "non vérifié" dans le dashboard.
# Source : top capitalisations S&P 500 + Nasdaq 100 + 22 tickers perso.
VALID_TICKERS = {
    # ── Notre watchlist (22) ─────────────────────────────────────────────────
    "AAPL", "NVDA", "TSLA", "MSFT", "META", "AMZN", "GOOGL", "AMD",
    "AVGO", "QCOM", "INTC", "MU", "ASML", "TSM", "MRVL", "PLTR",
    "SMCI", "CRM", "SNOW", "TWLO", "ZS", "BABA",
    # ── S&P 500 top 60 ───────────────────────────────────────────────────────
    "JPM", "V", "JNJ", "UNH", "PG", "MA", "HD", "BAC", "XOM", "CVX",
    "LLY", "PFE", "ABBV", "MRK", "KO", "PEP", "TMO", "COST", "DHR",
    "ACN", "LIN", "TXN", "NEE", "VZ", "CSCO", "ABT", "UPS", "BMY",
    "RTX", "HON", "SPGI", "LOW", "INTU", "SBUX", "CAT", "DE", "GS",
    "MS", "WFC", "BLK", "C", "AXP", "USB", "PNC", "TGT", "WMT",
    "BRK", "BRKB", "T", "CMCSA", "MDT", "CVS", "CI", "HUM", "ANTM",
    "SYK", "ZTS", "ISRG", "BSX", "ELV", "MCK",
    # ── Nasdaq 100 supplémentaires ───────────────────────────────────────────
    "ADBE", "REGN", "GILD", "AMGN", "BIIB", "MRNA", "PANW", "FTNT",
    "CRWD", "OKTA", "DDOG", "NET", "TEAM", "WDAY", "NOW", "VEEV",
    "ZM", "DOCU", "ORCL", "IBM", "HPQ", "DELL", "STX", "WDC",
    "SWKS", "KLAC", "AMAT", "LRCX", "MCHP", "ON", "TER", "ENTG",
    "MPWR", "NFLX", "DIS", "PYPL", "SHOP", "UBER", "SNAP", "PINS",
    "SPOT", "ROKU", "COIN", "TTD", "RBLX", "HOOD",
    # ── Semi-conducteurs / Hardware ──────────────────────────────────────────
    "QRVO", "WOLF", "CREE", "SLAB", "MTSI", "ACLS", "ONTO", "FORM",
    "RMBS", "POWI", "DIOD", "IXYS",
    # ── Énergie / Matières premières ─────────────────────────────────────────
    "OXY", "SLB", "HAL", "BKR", "EOG", "COP", "PSX", "MPC", "VLO",
    "DVN", "FANG", "EQT", "FCX", "NEM", "GOLD",
    # ── Finance / Crypto-related ─────────────────────────────────────────────
    "MSTR", "MARA", "RIOT", "HUT", "CLSK", "SQ", "SOFI",
    # ── ETFs majeurs (signaux valides) ────────────────────────────────────────
    "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLK", "XLF",
    "ARKK", "SQQQ", "TQQQ", "SPXU", "UVXY",
    # ── Autos / Véhicules électriques ─────────────────────────────────────────
    "F", "GM", "RIVN", "LCID", "NIO", "XPEV", "LI",
    # ── Transports / Voyage ──────────────────────────────────────────────────
    "BA", "AAL", "DAL", "UAL", "LUV", "CCL", "RCL",
    # ── Retail / Consommation ────────────────────────────────────────────────
    "NKE", "LULU", "TJX", "ROST", "DECK", "GPS", "COLM",
    # ── Biotech / Santé ───────────────────────────────────────────────────────
    "BMRN", "ALNY", "VRTX", "SGEN", "INCY", "RARE", "FOLD",
    # ── Meme stocks historiques ───────────────────────────────────────────────
    "GME", "AMC", "BB", "NOK",
}

# ── Blacklist — faux tickers, acronymes, mots courants sur Reddit ─────────────
# Complète le TICKER_STOP de RedditScanner/main.py (communs aux deux).
# Ces mots ne sont JAMAIS des tickers valides, même s'ils sont en majuscules.
TICKER_BLACKLIST = {
    # Acronymes financiers
    "AI", "CEO", "CFO", "COO", "CTO", "IPO", "ETF", "ATH", "DD",
    "EPS", "EV", "PT", "PE", "PB", "FCF", "ROE", "ROI", "DCF",
    # Jargon Reddit / WSB
    "YOLO", "IMO", "FOMO", "TLDR", "FYI", "WSB", "HODL", "BTFD",
    # Termes de trading
    "BUY", "SELL", "HOLD", "LONG", "SHORT", "BULL", "BEAR",
    "CALL", "PUT", "CALLS", "PUTS", "OTM", "ITM", "ATM",
    "MOON", "PUMP", "DUMP", "ROCKET", "SQUEEZE", "GAMMA",
    # Monnaies / Macro
    "USD", "EUR", "GBP", "JPY", "CNY", "USA", "FED", "SEC",
    "FDIC", "GDP", "CPI", "NFP", "ADP", "ISM", "OTC",
    # Mots génériques souvent en majuscules sur Reddit
    "THE", "AND", "FOR", "ALL", "NEW", "TOP", "NOW", "ARE",
    "MOST", "WITH", "LIST", "HUGE", "MONEY", "BETA", "FLOW",
    "BEST", "NEXT", "EACH", "SOME", "LIVE", "TIME", "BACK",
    "HIGH", "VERY", "WHEN", "WILL", "FROM", "THIS", "THAT",
    "HAVE", "MORE", "THAN", "INTO", "OVER", "JUST", "BEEN",
    "ALSO", "WHAT", "ONLY", "WEEK", "YEAR", "LAST", "SAME",
    "MOVE", "EVEN", "RISK", "PLAY", "PICK", "IDEA", "GOOD",
    "REAL", "RATE", "OPEN", "GAIN", "LOSS", "ZERO", "STOP",
    "DOWN", "HALF", "NEWS", "ALERT", "ALERTS", "TARGET", "UPDATE",
    "MAIN", "EDIT", "FWIW", "AFAIK", "IIRC", "IMHO", "IIRC",
    # Mots anglais courants détectés comme faux tickers
    "WELL", "LOW", "CLOSE", "LIKE", "MAKE", "MADE", "MUCH",
    "THEM", "THEN", "YOUR", "SAFE", "CASH", "DEBT", "FUND",
    "BOND", "BANK", "GOLD", "CORE", "TECH", "GROW", "DROP",
    "PEAK", "DIPS", "FREE", "RUNS", "SAVE", "EASY", "FAST",
    "RARE", "SURE", "STAY", "KEEP", "CARE", "HOPE", "FEAR",
    "ONES", "TAKE", "TURN", "LIFE", "WORK",
    # Faux tickers observés en production
    "VIST", "FEMY", "SIVB",
    # Verbes, pronoms et mots courts courants en majuscules
    "ANY", "GET", "GOT", "HAS", "HAD", "HOW", "WHO", "WHY",
    "WAY", "DAY", "BIG", "OLD", "OWN", "SET", "TRY", "ASK",
    "RUN", "LET", "SAY", "USE", "MAN", "FAR", "END", "ADD",
    "AGO", "AVG",
    # Faux tickers détectés sur r/buzztickr
    "MAR", "JAN", "FEB", "APR", "MAY", "JUN", "JUL", "AUG",
    "SEP", "OCT", "NOV", "DEC", "VOO", "BEAR", "BULL",
}


def is_known_ticker(ticker: str) -> bool:
    """
    Retourne True si le ticker appartient à la liste VALID_TICKERS.
    Les tickers de la watchlist perso (WATCHLIST) sont aussi considérés connus.
    Ne prend PAS en compte la blacklist (celle-ci est filtrée en amont).
    """
    return ticker in VALID_TICKERS or ticker in set(WATCHLIST)


# Chemins possibles pour trouver ton scanner
SCANNER_PATHS = [
    Path(__file__).parent.parent / "RedditScanner",
    Path(__file__).parent.parent / "reddit-scanner",
    Path(__file__).parent.parent.parent / "RedditScanner",
    Path(__file__).parent.parent.parent / "reddit-scanner",
]


def find_scanner_dir():
    """Trouve le dossier du scanner Reddit."""
    for p in SCANNER_PATHS:
        if (p / "main.py").exists():
            return p
    return None


def run_scanner(scanner_dir, refresh=True, cache_ttl=1800):
    """Lance le scanner Reddit PRO v4."""
    cmd = [
        sys.executable, "main.py",
        "--cache-ttl", str(cache_ttl),
        "--prefer-new",
    ]
    if refresh:
        cmd.append("--refresh")

    try:
        import os
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd,
            cwd=str(scanner_dir),
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        if result.returncode != 0:
            print(f"  [Reddit] Erreur scanner : {result.stderr[:300]}")
            return False

        # Afficher le résumé
        for line in result.stdout.split("\n"):
            if any(line.startswith(e) for e in ("🐂", "🐻", "👤", "📊", "💾", "📈")):
                print(f"  [Reddit] {line}")

        return True

    except subprocess.TimeoutExpired:
        print("  [Reddit] Timeout (>2 min)")
        return False
    except Exception as e:
        print(f"  [Reddit] Erreur : {e}")
        return False


def read_watchlist(scanner_dir):
    """Lit reddit_watchlist.csv."""
    csv_path = scanner_dir / "reddit_watchlist.csv"
    if not csv_path.exists():
        return None
    try:
        return pd.read_csv(csv_path)
    except Exception as e:
        print(f"  [Reddit] Erreur CSV : {e}")
        return None


def read_signals(scanner_dir):
    """Lit reddit_sentiment_signals.json."""
    json_path = scanner_dir / "reddit_sentiment_signals.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [Reddit] Erreur JSON : {e}")
        return None


def format_reddit_section(refresh=True):
    """
    Lance le scanner, lit les résultats, formate pour le morning scan.
    Retourne un string formaté ou None si indisponible.
    """
    if not PANDAS_AVAILABLE:
        print("  [Reddit] pandas non installé. Lance : pip install pandas")
        return None

    scanner_dir = find_scanner_dir()
    if scanner_dir is None:
        print("  [Reddit] Scanner non trouvé.")
        print(f"  [Reddit] Chemins testés :")
        for p in SCANNER_PATHS:
            print(f"    {p} → {'TROUVÉ' if (p / 'main.py').exists() else 'non'}")
        return None

    print(f"  [Reddit] Scanner trouvé : {scanner_dir}")

    # Lancer le scan
    if refresh:
        success = run_scanner(scanner_dir, refresh=True, cache_ttl=1800)
        if not success:
            # Réessayer avec le cache
            print("  [Reddit] Scan frais échoué, essai avec cache...")
            run_scanner(scanner_dir, refresh=False, cache_ttl=7200)

    # Lire les résultats
    df = read_watchlist(scanner_dir)
    if df is None or df.empty:
        print("  [Reddit] Pas de données dans reddit_watchlist.csv")
        return None

    signals = read_signals(scanner_dir)

    # === FORMATER ===
    lines = [
        f"{EMOJI_FIRE} *REDDIT BUZZ* (13 subreddits)",
        "",
    ]

    # Sentiment global
    if signals:
        total_bull = sum(d.get("sentiment_summary", {}).get("bullish", 0) for d in signals)
        total_bear = sum(d.get("sentiment_summary", {}).get("bearish", 0) for d in signals)
        total_ins = sum(d.get("sentiment_summary", {}).get("insider_buy", 0) for d in signals)
        net = total_bull - total_bear

        emoji = EMOJI_BULL if net > 0 else EMOJI_BEAR if net < 0 else EMOJI_NEUTRAL
        lines.append(f"{emoji} Sentiment : {net:+d} (bull:{total_bull} bear:{total_bear} insider:{total_ins})")
        lines.append("")

    # Tes tickers qui buzzent
    watchlist_set = set(WATCHLIST)
    my_tickers = df[df["Ticker"].isin(watchlist_set)].sort_values("Mentions", ascending=False)

    if not my_tickers.empty:
        lines.append("*Tes tickers :*")
        for _, row in my_tickers.head(5).iterrows():
            ticker = row["Ticker"]
            mentions = int(row["Mentions"])
            net_sent = int(row.get("Net_Sentiment", 0))
            style = row.get("Trade_Style", "?")
            emoji = EMOJI_BULL if net_sent > 0 else EMOJI_BEAR if net_sent < 0 else EMOJI_NEUTRAL
            lines.append(f"  {emoji} *{ticker}* — {mentions} mentions | sent:{net_sent:+d} | {style}")
        lines.append("")

    # Top tickers hors watchlist
    other = df[~df["Ticker"].isin(watchlist_set)].sort_values("Mentions", ascending=False)
    top_others = other.head(5)

    if not top_others.empty:
        lines.append("*Buzz hors watchlist :*")
        for _, row in top_others.iterrows():
            ticker = row["Ticker"]
            mentions = int(row["Mentions"])
            style = row.get("Trade_Style", "?")
            lines.append(f"  👀 {ticker} — {mentions} mentions | {style}")

    return "\n".join(lines)


def scan_buzztickers() -> list:
    """Scrape r/buzztickers pour trouver les tickers trending."""
    import requests
    import re
    url = "https://www.reddit.com/r/buzztickr/new.json?limit=10"
    headers = {"User-Agent": "SMC-AI-Scanner/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        tickers_found = {}
        for post in data["data"]["children"]:
            title    = post["data"].get("title", "")
            selftext = post["data"].get("selftext", "")
            full_text = title + " " + selftext
            # $TICKER pattern first (high confidence), then plain uppercase words
            found = re.findall(r'\$([A-Z]{2,5})', full_text)
            found += re.findall(r'\b([A-Z]{2,5})\b', full_text)
            for t in found:
                t = t.upper()
                if t not in TICKER_BLACKLIST and len(t) >= 2:
                    tickers_found[t] = tickers_found.get(t, 0) + 1
        results = [{"ticker": t, "mentions": c, "source": "buzztickers"}
                   for t, c in sorted(tickers_found.items(), key=lambda x: -x[1])]
        print(f"  [buzztickers] {len(results)} tickers trouvés : {[r['ticker'] for r in results[:10]]}")
        return results
    except Exception as e:
        print(f"  [buzztickers] Erreur: {e}")
        return []


def get_reddit_discoveries(
    min_mentions_reddit:   int = 2,
    min_mentions_buzz:     int = 1,
) -> list[dict]:
    """
    Retourne les tickers HORS watchlist découverts sur Reddit + r/buzztickr.

    Logique :
      - Source 1 (Reddit CSV) : hors watchlist, >= min_mentions_reddit, hors blacklist
      - Source 2 (buzztickr)  : hors watchlist, >= min_mentions_buzz, hors blacklist
        → PAS de filtre market_cap ni verify_ticker pour buzztickr (signal trending suffisant)
      - Fusion : si ticker dans les deux → source="both", mentions additives
      - Enrichissement LÉGER : price + change_pct via yfinance history(2d) seulement
        (pas de market_cap, pas de sector, pas de tk.info — trop lent)
      - Tri : "both" d'abord, puis par mentions décroissantes
      - Retourne top 20 (max)
    """
    watchlist_set = set(WATCHLIST)

    # ── Source 1 : Reddit CSV ─────────────────────────────────────────────────
    all_discoveries: list[dict] = []

    if PANDAS_AVAILABLE:
        scanner_dir = find_scanner_dir()
        df = read_watchlist(scanner_dir) if scanner_dir else None
        if df is not None and not df.empty:
            outside = df[~df["Ticker"].str.upper().isin(watchlist_set)].copy()
            outside["_ticker"] = outside["Ticker"].str.upper()
            outside = outside[outside["Mentions"].fillna(0).astype(int) >= min_mentions_reddit]
            outside = outside.sort_values("Mentions", ascending=False)
            print(f"  [Discoveries] Reddit CSV : {len(outside)} candidats hors watchlist >= {min_mentions_reddit} mentions")
            for _, row in outside.head(30).iterrows():
                ticker = str(row.get("_ticker", row.get("Ticker", ""))).strip().upper()
                if not ticker or ticker in TICKER_BLACKLIST:
                    continue
                mentions = int(row.get("Mentions", 0))
                net_sent = int(row.get("Net_Sentiment", 0))
                subs_raw = row.get("Subreddits", "")
                subs     = [s.strip() for s in str(subs_raw).split(",")
                            if s.strip() and str(subs_raw) != "nan"]
                all_discoveries.append({
                    "ticker":          ticker,
                    "mentions":        mentions,
                    "net_sentiment":   net_sent,
                    "sentiment_label": "BULL" if net_sent > 0 else "BEAR" if net_sent < 0 else "NEUTRAL",
                    "trade_style":     str(row.get("Trade_Style", "?")),
                    "subreddits":      subs,
                    "source":          "reddit",
                    "price":           None,
                    "change_pct":      None,
                    "dist_sma200":     None,
                    "vol_relative":    None,
                    "market_cap":      None,
                    "market_cap_str":  None,
                    "sector":          None,
                    "verified":        True,
                })
        else:
            print("  [Discoveries] Reddit CSV : aucune donnée disponible")
    else:
        print("  [Discoveries] Reddit CSV : pandas non disponible")

    csv_tickers = {d["ticker"] for d in all_discoveries}
    print(f"  [Discoveries] Source Reddit CSV : {len(all_discoveries)} tickers")

    # ── Source 2 : buzztickr ──────────────────────────────────────────────────
    buzz_results = scan_buzztickers()
    added_buzz = 0
    for r in buzz_results:
        ticker = r["ticker"]
        if ticker in TICKER_BLACKLIST or ticker in watchlist_set:
            continue
        if r["mentions"] < min_mentions_buzz:
            continue
        existing = next((d for d in all_discoveries if d["ticker"] == ticker), None)
        if existing:
            existing["mentions"] += r["mentions"]
            existing["source"]    = "both"
        else:
            all_discoveries.append({
                "ticker":          ticker,
                "mentions":        r["mentions"],
                "net_sentiment":   0,
                "sentiment_label": "NEUTRAL",
                "trade_style":     "?",
                "subreddits":      [],
                "source":          "buzztickers",
                "price":           None,
                "change_pct":      None,
                "dist_sma200":     None,
                "vol_relative":    None,
                "market_cap":      None,
                "market_cap_str":  None,
                "sector":          None,
                "verified":        True,
            })
            added_buzz += 1

    print(f"  [Discoveries] Source buzztickr : {len(buzz_results)} bruts, {added_buzz} nouveaux ajoutés")
    print(f"  [Discoveries] Total avant enrichissement : {len(all_discoveries)} tickers")

    # ── Tri : "both" d'abord, puis mentions ───────────────────────────────────
    all_discoveries.sort(key=lambda x: (x["source"] == "both", x["mentions"]), reverse=True)
    top = all_discoveries[:20]

    # ── Enrichissement LÉGER : price + change_pct seulement ──────────────────
    try:
        import yfinance as yf
        _yf_ok = True
    except ImportError:
        _yf_ok = False

    enriched_count = 0
    for d in top:
        if not _yf_ok:
            break
        try:
            hist = yf.Ticker(d["ticker"]).history(period="5d", interval="1d")
            if hist is not None and len(hist) >= 1:
                d["price"] = round(float(hist["Close"].iloc[-1]), 2)
                if len(hist) >= 2:
                    pc = float(hist["Close"].iloc[-2])
                    lc = float(hist["Close"].iloc[-1])
                    if pc > 0:
                        d["change_pct"] = round((lc - pc) / pc * 100, 2)
                # SMA200 si assez d'historique
                if len(hist) >= 20:
                    avg_vol  = float(hist["Volume"].tail(20).mean())
                    last_vol = float(hist["Volume"].iloc[-1])
                    if avg_vol > 0:
                        d["vol_relative"] = round(last_vol / avg_vol, 2)
                enriched_count += 1
        except Exception:
            pass  # price reste None — affiché "—" dans le dashboard

    print(f"  [Discoveries] Enrichissement yfinance : {enriched_count}/{len(top)} tickers enrichis")
    print(f"  [Discoveries] Résultat final : {len(top)} trouvailles")
    for d in top[:10]:
        print(f"    {d['ticker']:6s}  mentions={d['mentions']:3d}  source={d['source']:12s}  price={d['price']}")

    return top


# ── Cache module-level pour scan_reddit_direct ────────────────────────────────
_DIRECT_CACHE: dict = {"data": None, "expires": 0.0}


def scan_reddit_direct(cache_ttl: int = 1800) -> dict:
    """
    Scrape directement Reddit (JSON public) — source principale pour /api/reddit.
    Plus rapide et fiable que le subprocess RedditScanner (pas de CSV intermédiaire).

    Retourne {
      watchlist_results: [{ticker, mentions, net_sentiment, sentiment_label,
                            trade_style, subreddits, in_watchlist, verified, ...}],
      discovery_results: [...],   # tickers hors watchlist, triés par mentions
      scanned_at: str,
      total_posts: int,
      from_cache: bool
    }
    TTL cache : cache_ttl secondes (défaut 30 min).
    """
    import requests
    import re
    import time as _time
    from datetime import datetime

    now = _time.time()

    # Retourner le cache si encore valide
    if _DIRECT_CACHE["data"] is not None and now < _DIRECT_CACHE["expires"]:
        result = dict(_DIRECT_CACHE["data"])
        result["from_cache"] = True
        remaining = int(_DIRECT_CACHE["expires"] - now)
        print(f"  [reddit_direct] Cache valide ({remaining}s restantes)")
        return result

    SUBREDDITS = [
        "stocks", "wallstreetbets", "investing",
        "Daytrading", "StockMarket", "options", "buzztickr",
    ]
    watchlist_set = set(t.upper() for t in WATCHLIST)
    headers = {"User-Agent": "SMC-AI-Scanner/2.0"}

    ticker_data: dict = {}   # ticker → {mentions, score_sum, upvote_sum, count, subreddits}
    total_posts = 0

    for sub in SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=50"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"  [reddit_direct] {sub}: HTTP {resp.status_code}")
                continue
            posts = resp.json().get("data", {}).get("children", [])
            total_posts += len(posts)
            for post in posts:
                pd_ = post["data"]
                title        = pd_.get("title", "")
                score        = int(pd_.get("score", 0))
                upvote_ratio = float(pd_.get("upvote_ratio", 0.5))

                # $TICKER (haute confiance) puis mots majuscules
                found = set(re.findall(r'\$([A-Z]{2,5})', title))
                found |= set(re.findall(r'\b([A-Z]{2,5})\b', title))

                for t in found:
                    if t in TICKER_BLACKLIST or len(t) < 2 or len(t) > 5:
                        continue
                    if t not in ticker_data:
                        ticker_data[t] = {
                            "mentions": 0, "score_sum": 0,
                            "upvote_sum": 0.0, "count": 0, "subreddits": set(),
                        }
                    ticker_data[t]["mentions"]    += 1
                    ticker_data[t]["score_sum"]   += score
                    ticker_data[t]["upvote_sum"]  += upvote_ratio
                    ticker_data[t]["count"]       += 1
                    ticker_data[t]["subreddits"].add(sub)

            print(f"  [reddit_direct] {sub}: {len(posts)} posts")
        except Exception as e:
            print(f"  [reddit_direct] {sub}: erreur {e}")

    print(f"  [reddit_direct] Total : {total_posts} posts, {len(ticker_data)} tickers bruts")

    watchlist_results: list[dict] = []
    discovery_results: list[dict] = []

    for ticker, td in ticker_data.items():
        mentions   = td["mentions"]
        count      = td["count"] or 1
        avg_score  = td["score_sum"] / count
        avg_upvote = td["upvote_sum"] / count

        if avg_upvote > 0.70 and avg_score > 50:
            net_sentiment   = max(1, int(avg_score / 20))
            sentiment_label = "BULL"
        elif avg_upvote < 0.40:
            net_sentiment   = -max(1, int(abs(avg_score) / 20))
            sentiment_label = "BEAR"
        else:
            net_sentiment   = 0
            sentiment_label = "NEUTRAL"

        entry = {
            "ticker":          ticker,
            "mentions":        mentions,
            "net_sentiment":   net_sentiment,
            "sentiment_label": sentiment_label,
            "trade_style":     "SWING" if mentions > 3 else "DAY" if mentions >= 2 else "?",
            "subreddits":      sorted(td["subreddits"]),
            "in_watchlist":    ticker in watchlist_set,
            "verified":        is_known_ticker(ticker),
            "source":          "reddit_direct",
            "cross_validated": False,
            "trend":           "NEW",
            "trend_pct":       None,
            "mentions_avg_5d": None,
            "is_temp":         False,
        }

        if ticker in watchlist_set:
            watchlist_results.append(entry)
        elif mentions >= 1:
            discovery_results.append(entry)

    # Trier watchlist par mentions décroissantes
    watchlist_results.sort(key=lambda x: -x["mentions"])

    # Compléter la watchlist avec les tickers à 0 mentions
    found_wl = {r["ticker"] for r in watchlist_results}
    for tk in sorted(watchlist_set):
        if tk not in found_wl:
            watchlist_results.append({
                "ticker": tk, "mentions": 0, "net_sentiment": 0,
                "sentiment_label": "NEUTRAL", "trade_style": "—",
                "subreddits": [], "in_watchlist": True, "verified": True,
                "source": "reddit_direct", "cross_validated": False,
                "trend": "NEW", "trend_pct": None, "mentions_avg_5d": None,
                "is_temp": False,
            })

    discovery_results.sort(key=lambda x: -x["mentions"])

    print(f"  [reddit_direct] Résultat : "
          f"{sum(1 for r in watchlist_results if r['mentions'] > 0)} watchlist actifs, "
          f"{len(discovery_results[:20])} trouvailles")

    result = {
        "watchlist_results": watchlist_results,
        "discovery_results": discovery_results[:20],
        "scanned_at":        datetime.now().isoformat(),
        "total_posts":       total_posts,
        "from_cache":        False,
    }

    # Mettre en cache
    _DIRECT_CACHE["data"]    = result
    _DIRECT_CACHE["expires"] = now + cache_ttl

    return result


# === TEST ===
if __name__ == "__main__":
    print("=== TEST REDDIT WRAPPER ===\n")

    print("--- scan_buzztickers() ---")
    buzz = scan_buzztickers()
    for b in buzz[:10]:
        print(f"  {b['ticker']:6s}  {b['mentions']} mentions  [{b['source']}]")

    print("\n--- scan_reddit_direct() ---")
    direct = scan_reddit_direct(cache_ttl=0)   # cache_ttl=0 → scan frais à chaque test
    wl = [r for r in direct["watchlist_results"] if r["mentions"] > 0]
    print(f"  Watchlist actifs : {len(wl)}/{len(direct['watchlist_results'])} | Posts scannés : {direct['total_posts']}")
    print(f"  Depuis le cache : {direct['from_cache']}")
    for r in wl[:10]:
        sent = f"+{r['net_sentiment']}" if r['net_sentiment'] >= 0 else str(r['net_sentiment'])
        print(f"    {r['ticker']:6s}  {r['mentions']:3d} mentions  sent:{sent:>4s}  {','.join(r['subreddits'][:2])}")
    print(f"\n  Trouvailles ({len(direct['discovery_results'])}) :")
    for r in direct["discovery_results"][:10]:
        print(f"    {r['ticker']:6s}  {r['mentions']:3d} mentions  verified={r['verified']}")

    print("\n--- format_reddit_section() ---")
    section = format_reddit_section(refresh=False)
    if section:
        print(section)
    else:
        print("Scanner non trouvé ou pas de données.")