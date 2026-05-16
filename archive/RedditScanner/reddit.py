"""
Module Reddit — Intégration du Reddit Premarket Scanner PRO v4.

Ce module est un WRAPPER qui :
1. Lance ton scanner main.py existant (qui est dans le dossier reddit-scanner/)
2. Lit les fichiers CSV/JSON générés
3. Formate les résultats pour le morning scan

Prérequis :
  - Ton dossier reddit-scanner/ avec main.py doit être à côté de trading-agent/
    OU dans trading-agent/reddit-scanner/
  - pip install pandas requests beautifulsoup4

Structure attendue :
  trading-agent/
  ├── morning_scan.py
  ├── reddit-scanner/        ← ton scanner PRO v4
  │   ├── main.py
  │   └── cache/
  └── scrapers/
      └── reddit.py          ← ce fichier (wrapper)
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from config.settings import WATCHLIST, EMOJI_FIRE, EMOJI_BULL, EMOJI_BEAR, EMOJI_NEUTRAL


# Chemins possibles pour le scanner Reddit
SCANNER_PATHS = [
    Path(__file__).parent.parent / "reddit-scanner",     # trading-agent/reddit-scanner/
    Path(__file__).parent.parent.parent / "reddit-scanner",  # Bourse/reddit-scanner/
]


def find_scanner_dir():
    """Trouve le dossier du scanner Reddit."""
    for p in SCANNER_PATHS:
        if (p / "main.py").exists():
            return p
    return None


def run_scanner(refresh=True, cache_ttl=1800, prefer_new=True):
    """
    Lance le scanner Reddit PRO v4 et retourne le chemin du dossier.
    """
    scanner_dir = find_scanner_dir()
    if scanner_dir is None:
        return None

    cmd = [
        sys.executable, "main.py",
        "--cache-ttl", str(cache_ttl),
        "--prefer-new",
    ]
    if refresh:
        cmd.append("--refresh")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(scanner_dir),
            capture_output=True,
            text=True,
            timeout=120,  # 2 min max
        )

        if result.returncode != 0:
            print(f"  [Reddit] Scanner erreur : {result.stderr[:200]}")
            return None

        # Afficher un résumé de la sortie du scanner
        for line in result.stdout.split("\n"):
            if line.startswith(("🐂", "🐻", "👤", "📊", "💾")):
                print(f"  [Reddit] {line}")

        return scanner_dir

    except subprocess.TimeoutExpired:
        print("  [Reddit] Scanner timeout (>2 min)")
        return None
    except Exception as e:
        print(f"  [Reddit] Erreur lancement : {e}")
        return None


def read_watchlist(scanner_dir):
    """Lit le fichier reddit_watchlist.csv généré par le scanner."""
    csv_path = scanner_dir / "reddit_watchlist.csv"
    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path)
        return df
    except Exception as e:
        print(f"  [Reddit] Erreur lecture CSV : {e}")
        return None


def read_signals(scanner_dir):
    """Lit le fichier reddit_sentiment_signals.json."""
    json_path = scanner_dir / "reddit_sentiment_signals.json"
    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [Reddit] Erreur lecture JSON : {e}")
        return None


def format_reddit_section(refresh=True):
    """
    Lance le scanner, lit les résultats, formate pour le morning scan.
    Retourne un string formaté ou None si le scanner n'est pas trouvé.
    """
    scanner_dir = find_scanner_dir()
    if scanner_dir is None:
        print("  [Reddit] Scanner non trouvé.")
        print(f"  [Reddit] Chemins testés : {[str(p) for p in SCANNER_PATHS]}")
        print("  [Reddit] Place ton reddit-scanner/ dans trading-agent/ ou Bourse/")
        return None

    # Lire les résultats existants (ou lancer un scan frais)
    if refresh:
        print(f"  [Reddit] Lancement du scanner ({scanner_dir})...")
        result_dir = run_scanner(refresh=True, cache_ttl=1800)
        if result_dir is None:
            # Essayer avec le cache
            print("  [Reddit] Scan frais échoué, tentative avec cache...")
            result_dir = run_scanner(refresh=False, cache_ttl=7200)
    else:
        result_dir = scanner_dir

    if result_dir is None:
        return None

    # Lire la watchlist
    df = read_watchlist(result_dir)
    if df is None or df.empty:
        return None

    # Lire les signaux pour le résumé global
    signals = read_signals(result_dir)

    # Formater la section
    lines = [
        f"{EMOJI_FIRE} *REDDIT BUZZ* (13 subreddits scannés)",
        "",
    ]

    # Résumé global du sentiment
    if signals:
        total_bull = sum(d.get("sentiment_summary", {}).get("bullish", 0) for d in signals)
        total_bear = sum(d.get("sentiment_summary", {}).get("bearish", 0) for d in signals)
        total_ins = sum(d.get("sentiment_summary", {}).get("insider_buy", 0) for d in signals)
        net = total_bull - total_bear

        sentiment_emoji = EMOJI_BULL if net > 0 else EMOJI_BEAR if net < 0 else EMOJI_NEUTRAL
        lines.append(f"{sentiment_emoji} Sentiment global : {net:+d} (bull:{total_bull} bear:{total_bear} insider:{total_ins})")
        lines.append("")

    # Top tickers de ta watchlist qui buzzent
    watchlist_set = set(WATCHLIST)
    my_tickers = df[df["Ticker"].isin(watchlist_set)].sort_values("Mentions", ascending=False)

    if not my_tickers.empty:
        lines.append("*Tes tickers :*")
        for _, row in my_tickers.head(5).iterrows():
            ticker = row["Ticker"]
            mentions = int(row["Mentions"])
            net_sent = int(row.get("Net_Sentiment", 0))
            swing = int(row.get("Swing_Score", 0))
            pump = int(row.get("Pump_Score", 0))
            style = row.get("Trade_Style", "?")

            emoji = EMOJI_BULL if net_sent > 0 else EMOJI_BEAR if net_sent < 0 else EMOJI_NEUTRAL
            lines.append(f"  {emoji} *{ticker}* — {mentions} mentions | sent:{net_sent:+d} | {style}")
        lines.append("")

    # Top tickers globaux (hors watchlist) les plus mentionnés
    other_tickers = df[~df["Ticker"].isin(watchlist_set)].sort_values("Mentions", ascending=False)
    top_others = other_tickers.head(5)

    if not top_others.empty:
        lines.append("*Buzz hors watchlist :*")
        for _, row in top_others.iterrows():
            ticker = row["Ticker"]
            mentions = int(row["Mentions"])
            style = row.get("Trade_Style", "?")
            lines.append(f"  👀 {ticker} — {mentions} mentions | {style}")

    return "\n".join(lines)


# === TEST ===
if __name__ == "__main__":
    print("=== TEST REDDIT WRAPPER ===\n")
    section = format_reddit_section(refresh=False)
    if section:
        print(section)
    else:
        print("Scanner non trouvé ou pas de données.")
        print("Assure-toi que reddit-scanner/main.py existe.")
