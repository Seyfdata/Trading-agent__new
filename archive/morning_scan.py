"""
Morning Scan v3 — PRO Brief

Rapport complet pre-market pour swing trader SMC :
1. Calendrier macro (événements + verdict GO/PRUDENCE/NO TRADE)
2. Market Context (SPY, QQQ, VIX, DXY, US10Y + verdict marché)
3. TOP 3 DU JOUR (scores composites via analysis/scoring.py)
4. Watchlist Scanner (22 tickers : prix, variation, SMA200, volume)
5. Setup Candidates (tickers à regarder en priorité sur TradingView)
6. Reddit Buzz (13 subreddits : sentiment + tickers qui buzzent)
7. News par tickers + news marché (10 flux RSS)
8. Checklist pre-market

Usage :
    python morning_scan.py
"""

from datetime import datetime
from scrapers.rss_news import fetch_and_filter
from scrapers.macro_calendar import (
    format_macro_section, detect_recurring_events,
    check_earnings_today, get_trading_recommendation
)
from scrapers.reddit import (
    format_reddit_section, find_scanner_dir,
    read_watchlist as read_reddit_watchlist,
)
from scrapers.market_data import (
    get_market_context, scan_watchlist,
    format_market_context, format_watchlist_scanner,
    find_setup_candidates, format_setup_candidates,
)
from notifications.telegram import send_message
from config.settings import (
    WATCHLIST, EMOJI_NEWS, EMOJI_BULL, EMOJI_WARNING,
    EMOJI_NEUTRAL, EMOJI_CHART, EMOJI_FIRE, TELEGRAM_ENABLED
)

try:
    from analysis.scoring import score_ticker, score_market_context, rank_tickers
    from database.models import init_db, save_scores, save_market_context
    SCORING_AVAILABLE = True
except ImportError as _e:
    SCORING_AVAILABLE = False
    print(f"[Scoring] Module non disponible : {_e}")


# ── Helpers scoring ─────────────────────────────────────────────────────────

def _build_reddit_data_map(scanner_dir) -> dict:
    """
    Construit {ticker: {mentions, sentiment}} depuis le CSV Reddit.
    Retourne {} si le scanner n'est pas disponible.
    """
    if scanner_dir is None:
        return {}
    try:
        df = read_reddit_watchlist(scanner_dir)
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            if not ticker:
                continue
            mentions = int(row.get("Mentions", 0))
            net_sent = float(row.get("Net_Sentiment", 0))
            # Normalize : net_sent est un compte brut, on ramène à [-1, 1]
            sentiment = max(-1.0, min(1.0, net_sent / max(mentions, 1)))
            result[ticker] = {"mentions": mentions, "sentiment": sentiment}
        return result
    except Exception:
        return {}


def _build_news_data_map(ticker_news: list, keyword_news: list) -> dict:
    """
    Construit {ticker: {ticker_matches, keyword_matches}} depuis les listes de news.
    """
    result = {}
    for news in ticker_news:
        for t in news.get("matched_tickers", []):
            entry = result.setdefault(t, {"ticker_matches": 0, "keyword_matches": 0})
            entry["ticker_matches"] += 1
    for news in keyword_news:
        for t in news.get("matched_tickers", []):
            entry = result.setdefault(t, {"ticker_matches": 0, "keyword_matches": 0})
            entry["keyword_matches"] += 1
    return result


def _top3_detail(scored: dict, reddit_map: dict, scan_map: dict) -> str:
    """Construit la chaîne de détail synthétique pour l'affichage TOP 3."""
    ticker = scored["ticker"]
    hints = []

    # Volume anormal
    if scored["volume_score"] >= 18:
        rel_vol = scan_map.get(ticker, {}).get("vol_relative", 0)
        if rel_vol:
            pct = int((rel_vol - 1) * 100)
            hints.append(f"vol +{pct}%")

    # Reddit actif
    if scored["reddit_score"] >= 12:
        mentions = reddit_map.get(ticker, {}).get("mentions", 0)
        if mentions:
            hints.append(f"Reddit x{mentions}")

    # Position SMA200
    if scored["sma200_score"] >= 18:
        dist = scan_map.get(ticker, {}).get("dist_sma200")
        if dist is not None:
            hints.append(f"SMA200 {dist:+.1f}%")

    # News forte
    if scored["news_score"] >= 20:
        n = scored["news_score"] // 7
        hints.append(f"{n} news ticker")

    return ", ".join(hints) if hints else scored["components"].get("sma200_detail", "")


def format_top3_section(ranked: list, reddit_map: dict = None, scan_map: dict = None) -> str:
    """Formate la section 🏆 TOP 3 DU JOUR."""
    if not ranked:
        return None

    reddit_map = reddit_map or {}
    scan_map = scan_map or {}

    lines = ["🏆 *TOP 3 DU JOUR*", ""]

    for item in [r for r in ranked if r["top3"]]:
        n = item["rank"]
        ticker = item["ticker"]
        score = item["total_score"]
        detail = _top3_detail(item, reddit_map, scan_map)
        suffix = f" ({detail})" if detail else ""
        lines.append(f"{n}. *{ticker}* — Score {score}{suffix}")

    return "\n".join(lines)


# ── Formatage du rapport ─────────────────────────────────────────────────────

def format_report(
    macro_text,
    market_text, watchlist_text, candidates_text,
    reddit_text,
    ticker_news, keyword_news, combined, all_count,
    top3_text=None, regime=None, market_score=None,
):
    """Formate le rapport complet PRO Brief."""

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Header v2
    header = f"🎯 *MORNING BRIEF v2* | {now}"
    if regime and market_score is not None:
        header += f"\n🌍 *CONTEXTE : {regime}* (score {market_score}/100)"

    lines = [
        header,
        "",
        "=" * 35,
        "",
    ]

    # 1. MACRO
    lines.append(macro_text)
    lines.append("")
    lines.append("=" * 35)
    lines.append("")

    # 2. MARKET CONTEXT
    if market_text:
        lines.append(market_text)
        lines.append("")
        lines.append("=" * 35)
        lines.append("")

    # 3. TOP 3 DU JOUR (entre Market Context et Watchlist)
    if top3_text:
        lines.append(top3_text)
        lines.append("")
        lines.append("=" * 35)
        lines.append("")

    # 4. WATCHLIST SCANNER
    if watchlist_text:
        lines.append(watchlist_text)
        lines.append("")
        lines.append("=" * 35)
        lines.append("")

    # 5. SETUP CANDIDATES
    if candidates_text:
        lines.append(candidates_text)
        lines.append("")
        lines.append("=" * 35)
        lines.append("")

    # 6. REDDIT BUZZ
    if reddit_text:
        lines.append(reddit_text)
        lines.append("")
        lines.append("=" * 35)
        lines.append("")

    # 7. NEWS TICKERS
    if ticker_news:
        lines.append(f"{EMOJI_FIRE} *NEWS TICKERS*")
        lines.append("")
        for news in ticker_news[:5]:
            tickers = ", ".join(news.get("matched_tickers", []))
            lines.append(f"{EMOJI_BULL} *[{tickers}]* {news['title']}")
            lines.append(f"  _{news['source']}_")
            lines.append("")

    ticker_titles = {n["title"] for n in ticker_news}
    keyword_only = [n for n in keyword_news if n["title"] not in ticker_titles]
    if keyword_only:
        lines.append(f"{EMOJI_NEWS} *NEWS MARCHÉ*")
        lines.append("")
        for news in keyword_only[:3]:
            keywords = ", ".join(news.get("matched_keywords", [])[:3])
            lines.append(f"{EMOJI_NEUTRAL} [{keywords}] {news['title']}")
            lines.append(f"  _{news['source']}_")
            lines.append("")

    # 8. CHECKLIST
    lines.extend([
        "=" * 35,
        "",
        f"{EMOJI_WARNING} *Checklist pre-market :*",
        "• Confirmer la macro sur ForexFactory.com",
        "• Analyser les Setup Candidates sur TradingView",
        "• Préparer les niveaux (OB, FVG, liquidité)",
        "• Pre-market : 13h-14h30 CET (analyse)",
        "• Killzone : 14h30-16h30 CET (exécution)",
        "• Risque max selon verdict macro",
    ])

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    """Exécute le Morning Brief PRO complet."""

    start = datetime.now()
    print(f"[{start.strftime('%H:%M:%S')}] Morning Brief PRO démarré...")
    print(f"  Date : {start.strftime('%A %d/%m/%Y')}")
    print()

    # ── 0. Initialisation DB ──────────────────────────────────────────────
    if SCORING_AVAILABLE:
        try:
            init_db()
        except Exception as e:
            print(f"  [DB] init_db erreur : {e}")

    # ── 1. Calendrier macro ───────────────────────────────────────────────
    print("  1. Calendrier macro...")
    macro_text = format_macro_section()
    events = detect_recurring_events()
    earnings = check_earnings_today()
    reco = get_trading_recommendation(events, earnings)
    print(f"     Verdict : {reco['verdict']}")
    print()

    # ── 2. Market Data (données brutes conservées pour le scoring) ────────
    print("  2. Market Data...")
    context = None
    scan = None
    market_text = watchlist_text = candidates_text = None
    try:
        print("     Niveau 1 : Market Context...")
        context = get_market_context()
        market_text = format_market_context(context)

        print("     Niveau 2 : Watchlist Scanner...")
        scan = scan_watchlist()
        watchlist_text = format_watchlist_scanner(scan)

        print("     Niveau 3 : Setup Candidates...")
        candidates = find_setup_candidates(scan)
        candidates_text = format_setup_candidates(candidates)
    except Exception as e:
        print(f"     Market Data erreur : {e}")
    print()

    # ── 3. Reddit Buzz ────────────────────────────────────────────────────
    print("  3. Reddit Buzz...")
    reddit_text = None
    scanner_dir = None
    try:
        scanner_dir = find_scanner_dir()
        reddit_text = format_reddit_section()
        print("     Reddit OK" if reddit_text else "     Reddit skip")
    except Exception as e:
        print(f"     Reddit erreur : {e}")
    print()

    # ── 4. News RSS ───────────────────────────────────────────────────────
    print("  4. News RSS (10 sources)...")
    all_news, ticker_news, keyword_news, combined = fetch_and_filter(max_per_feed=5)
    print(f"     {len(all_news)} news → {len(ticker_news)} tickers + {len(keyword_news)} keywords")
    print()

    # ── 5. Scoring composite ──────────────────────────────────────────────
    top3_text = None
    regime = None
    market_score_val = None

    if SCORING_AVAILABLE:
        print("  5. Scoring composite...")
        try:
            # Contexte marché
            scoring_ctx = {}
            if context:
                vix_info = context.get("^VIX")
                spy_info = context.get("SPY")
                dxy_info = context.get("DX-Y.NYB")
                tny_info = context.get("^TNX")
                if vix_info and "price" in vix_info:
                    scoring_ctx["vix"] = vix_info["price"]
                if spy_info and "change_pct" in spy_info:
                    scoring_ctx["spy_change"] = spy_info["change_pct"]
                if dxy_info and "price" in dxy_info:
                    scoring_ctx["dxy"] = dxy_info["price"]
                if tny_info and "price" in tny_info:
                    scoring_ctx["us10y"] = tny_info["price"]

            ctx_scored = score_market_context(scoring_ctx)
            regime = ctx_scored["regime"]
            market_score_val = ctx_scored["score"]

            # Maps de données brutes par ticker
            reddit_map = _build_reddit_data_map(scanner_dir)
            news_map = _build_news_data_map(ticker_news, keyword_news)
            scan_map = {r["ticker"]: r for r in (scan or []) if "error" not in r}

            # Scorer chaque ticker disponible dans le scan
            scored_list = []
            for r in (scan or []):
                if "error" in r:
                    continue
                ticker = r["ticker"]
                md = {
                    "current_price": r.get("price"),
                    "sma200": r.get("sma200"),
                    "price_vs_sma200_pct": r.get("dist_sma200"),
                    "volume": r.get("vol_today"),
                    "relative_volume": r.get("vol_relative"),
                }
                rd = reddit_map.get(ticker, {"mentions": 0, "sentiment": 0.0})
                nd = news_map.get(ticker, {"ticker_matches": 0, "keyword_matches": 0})
                scored_list.append(score_ticker(ticker, md, rd, nd))

            ranked = rank_tickers(scored_list)
            top3_text = format_top3_section(ranked, reddit_map, scan_map)

            # Sauvegarde DB
            today = start.strftime("%Y-%m-%d")
            save_scores(today, scored_list)
            save_market_context(today, ctx_scored)

            print(f"     Scoring OK — {len(scored_list)} tickers | Régime : {regime} ({market_score_val}/100)")

        except Exception as e:
            print(f"     Scoring erreur (rapport envoyé sans scoring) : {e}")
    else:
        print("  5. Scoring (non disponible — modules manquants)")
    print()

    # ── 6. Formater ───────────────────────────────────────────────────────
    report = format_report(
        macro_text,
        market_text, watchlist_text, candidates_text,
        reddit_text,
        ticker_news, keyword_news, combined, len(all_news),
        top3_text=top3_text,
        regime=regime,
        market_score=market_score_val,
    )

    # ── 7. Afficher ───────────────────────────────────────────────────────
    print("=" * 60)
    print(report)
    print("=" * 60)

    # ── 8. Envoyer sur Telegram ───────────────────────────────────────────
    # Désactivé par défaut — mettre TELEGRAM_ENABLED = True dans settings.py
    if TELEGRAM_ENABLED:
        print("\n  Envoi sur Telegram...")
        if len(report) > 4000:
            mid = report.find("NEWS TICKERS")
            if mid > 0:
                send_message(report[:mid].rstrip())
                send_message(report[mid:])
            else:
                send_message(report[:4000])
                send_message(report[4000:])
        else:
            send_message(report)
    else:
        print("\n  Telegram désactivé (TELEGRAM_ENABLED=False dans settings.py)")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Morning Brief PRO terminé en {elapsed:.1f}s")


if __name__ == "__main__":
    main()
