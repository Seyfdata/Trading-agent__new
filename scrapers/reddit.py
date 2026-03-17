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


def get_reddit_discoveries(
    min_mentions:    int   = 3,
    min_market_cap:  float = 1e9,
) -> list[dict]:
    """
    Retourne les tickers HORS watchlist découverts sur Reddit.

    Critères :
      - Hors watchlist perso (WATCHLIST)
      - Dans VALID_TICKERS OU vérifiés par yfinance
      - PAS dans TICKER_BLACKLIST
      - >= min_mentions mentions
      - market_cap >= min_market_cap (défaut 1 Md$, filtre penny stocks)

    Enrichissement yfinance : price, change_pct, market_cap, sector.
    (Lent ~30-60s si 10 tickers avec sector — à lancer sur bouton manuel.)

    Retourne les top 10 triés par mentions décroissantes.
    """
    if not PANDAS_AVAILABLE:
        return []

    scanner_dir = find_scanner_dir()
    if scanner_dir is None:
        return []

    df = read_watchlist(scanner_dir)
    if df is None or df.empty:
        return []

    watchlist_set = set(WATCHLIST)

    # ── Candidats hors watchlist avec assez de mentions ───────────────────────
    outside = df[~df["Ticker"].isin(watchlist_set)].copy()
    outside = outside[outside["Mentions"].fillna(0).astype(int) >= min_mentions]
    outside = outside.sort_values("Mentions", ascending=False)

    try:
        import yfinance as yf
        _yf_ok = True
    except ImportError:
        _yf_ok = False

    discoveries: list[dict] = []

    for _, row in outside.head(30).iterrows():   # évalue jusqu'à 30 candidats
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        if ticker in TICKER_BLACKLIST:
            continue

        # Validation ticker (cache yfinance)
        known = is_known_ticker(ticker)
        if not known:
            known = verify_ticker(ticker)
        if not known:
            continue

        mentions  = int(row.get("Mentions", 0))
        net_sent  = int(row.get("Net_Sentiment", 0))
        style     = str(row.get("Trade_Style", "?"))
        subs_raw  = row.get("Subreddits", "")
        subs      = [s.strip() for s in str(subs_raw).split(",")
                     if s.strip() and str(subs_raw) != "nan"]

        # ── Enrichissement yfinance ───────────────────────────────────────────
        price = market_cap = change_pct = sector = None

        if _yf_ok:
            try:
                tk = yf.Ticker(ticker)
                fi = tk.fast_info

                if hasattr(fi, "last_price") and fi.last_price:
                    price = round(float(fi.last_price), 2)
                if hasattr(fi, "market_cap") and fi.market_cap:
                    market_cap = float(fi.market_cap)

                # Variation journalière
                hist = tk.history(period="2d", interval="1d")
                if hist is not None and len(hist) >= 2:
                    pc = float(hist["Close"].iloc[-2])
                    lc = float(hist["Close"].iloc[-1])
                    if pc > 0:
                        change_pct = round((lc - pc) / pc * 100, 2)

                # Secteur (plus lent — appel tk.info)
                try:
                    sector = tk.info.get("sector")
                except Exception:
                    sector = None

            except Exception:
                pass

        # Filtre market cap
        if market_cap is not None and market_cap < min_market_cap:
            continue

        # Formatage market cap lisible
        cap_str = None
        if market_cap:
            if market_cap >= 1e12:
                cap_str = f"${market_cap / 1e12:.1f}T"
            elif market_cap >= 1e9:
                cap_str = f"${market_cap / 1e9:.1f}B"
            else:
                cap_str = f"${market_cap / 1e6:.0f}M"

        discoveries.append({
            "ticker":          ticker,
            "mentions":        mentions,
            "net_sentiment":   net_sent,
            "sentiment_label": "BULL" if net_sent > 0 else "BEAR" if net_sent < 0 else "NEUTRAL",
            "trade_style":     style,
            "subreddits":      subs,
            "verified":        True,
            "market_cap":      market_cap,
            "market_cap_str":  cap_str,
            "sector":          sector,
            "price":           price,
            "change_pct":      change_pct,
        })

        if len(discoveries) >= 10:
            break

    return discoveries


# === TEST ===
if __name__ == "__main__":
    print("=== TEST REDDIT WRAPPER ===\n")
    section = format_reddit_section(refresh=False)
    if section:
        print(section)
    else:
        print("Scanner non trouvé ou pas de données.")