import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
import streamlit as st
import pandas as pd

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

st.set_page_config(page_title="Reddit Premarket Scanner", layout="wide")

SUMMARY_CSV = "reddit_signals_summary.csv"
WATCHLIST_CSV = "reddit_watchlist.csv"
SWING_CSV = "reddit_watchlist_swing.csv"
PUMP_CSV = "reddit_watchlist_pump.csv"
DETAIL_JSON = "reddit_sentiment_signals.json"
SNAP_DIR = "snapshots"

LANG = st.sidebar.selectbox("Language / Langue", ["EN", "FR"], index=0)
I18N = {
    "EN": {
        "title": "🕒 Reddit Premarket Scanner (PRO)",
        "subtitle": "Now includes dedup + snapshots history. Heuristics — not financial advice.",
        "run": "🔄 Run Premarket Scan",
        "controls": "⚙️ Premarket controls",
        "thresholds": "Shortlist thresholds",
        "cache_ttl": "Cache TTL (sec)",
        "prefer_new": "Prefer NEW (fresher)",
        "focus": "🎯 Focus tickers",
        "force_refresh": "💥 Force refresh",
        "half_life": "Time-decay half-life (hours)",
        "snapshot": "📦 Save snapshot",
        "snapshot_tag": "Snapshot tag",
        "auto_refresh": "🕐 Auto-refresh (market hours)",
        "auto_ui": "Auto-refresh UI",
        "interval": "UI interval (sec)",
        "missing": "❌ Missing files. Run scan to generate CSV/JSON.",
        "updated": "Last update",
        "tabs": ["🕒 Premarket", "📌 Overview", "👀 Watchlist", "📈 History", "🧾 Posts", "📚 Guide"],
        "swing": "🟦 Swing candidates",
        "pump": "🟥 Pump risk",
        "copy": "Tickers (copy/paste)",
        "links": "Quick links",
        "download_swing": "⬇️ Download swing CSV",
        "download_pump": "⬇️ Download pump CSV",
        "history_title": "📈 History (snapshots)",
        "pick_snap": "Pick a snapshot",
        "compare_with": "Compare with (optional)",
        "added": "Added",
        "removed": "Removed",
        "unchanged": "Unchanged",
    },
    "FR": {
        "title": "🕒 Reddit Premarket Scanner (PRO)",
        "subtitle": "Inclut maintenant dédup + historique snapshots. Heuristiques — pas un conseil financier.",
        "run": "🔄 Lancer le scan Premarket",
        "controls": "⚙️ Contrôles Premarket",
        "thresholds": "Seuils shortlist",
        "cache_ttl": "Cache TTL (sec)",
        "prefer_new": "Préférer NEW (plus frais)",
        "focus": "🎯 Focus tickers",
        "force_refresh": "💥 Forcer refresh",
        "half_life": "Demi-vie time-decay (heures)",
        "snapshot": "📦 Sauver snapshot",
        "snapshot_tag": "Tag snapshot",
        "auto_refresh": "🕐 Auto-refresh (heures marché)",
        "auto_ui": "Auto-refresh UI",
        "interval": "Intervalle UI (sec)",
        "missing": "❌ Fichiers manquants. Lance un scan pour générer CSV/JSON.",
        "updated": "Dernière mise à jour",
        "tabs": ["🕒 Premarket", "📌 Vue d’ensemble", "👀 Watchlist", "📈 Historique", "🧾 Posts", "📚 Guide"],
        "swing": "🟦 Candidats Swing",
        "pump": "🟥 Risque Pump",
        "copy": "Tickers (copier/coller)",
        "links": "Liens rapides",
        "download_swing": "⬇️ Télécharger CSV Swing",
        "download_pump": "⬇️ Télécharger CSV Pump",
        "history_title": "📈 Historique (snapshots)",
        "pick_snap": "Choisir un snapshot",
        "compare_with": "Comparer avec (optionnel)",
        "added": "Ajoutés",
        "removed": "Retirés",
        "unchanged": "Inchangés",
    },
}
t = lambda k: I18N[LANG].get(k, k)

@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in df.columns:
        if col in {
            "Bullish","Bearish","Insider_Buy","Net_Sentiment","Hype_Total",
            "Swing_Score","Pump_Score","Posts_Analyzed","Mentions","Duplicates_Skipped"
        }:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        if col in {"Weight_Sum","HalfLifeHours"}:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "Ticker" in df.columns:
        df["Ticker"] = df["Ticker"].astype(str).str.upper()
    return df

@st.cache_data
def load_details():
    if not os.path.exists(DETAIL_JSON):
        return []
    with open(DETAIL_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def tv_link(ticker: str) -> str:
    return f"https://www.tradingview.com/symbols/{ticker}/"

def yahoo_link(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}"

def file_mtime_str(path: str) -> str:
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"

def run_scrape(force_refresh: bool, cache_ttl: int, focus: bool, prefer_new: bool, half_life_hours: float,
              snapshot: bool, snapshot_tag: str,
              swing_min: int, pump_min: int, mentions_min: int, pump_max_for_swing: int,
              insider_min_for_swing: int, insider_max_for_pump: int):
    args = [
        sys.executable, "main.py",
        "--cache-ttl", str(cache_ttl),
        "--half-life-hours", str(half_life_hours),
        "--swing-min", str(swing_min),
        "--pump-min", str(pump_min),
        "--mentions-min", str(mentions_min),
        "--pump-max-for-swing", str(pump_max_for_swing),
        "--insider-min-for-swing", str(insider_min_for_swing),
        "--insider-max-for-pump", str(insider_max_for_pump),
    ]
    if force_refresh:
        args.append("--refresh")
    if focus:
        args.append("--focus")
    if prefer_new:
        args.append("--prefer-new")
    if snapshot:
        args.append("--snapshot")
        args += ["--snapshot-tag", snapshot_tag or "premarket"]

    proc = subprocess.run(args, capture_output=True, text=True)
    st.cache_data.clear()
    return proc

st.title(t("title"))
st.caption(t("subtitle"))

# Sidebar
st.sidebar.header(t("controls"))
cache_ttl = st.sidebar.selectbox(t("cache_ttl"), [900, 1800, 3600, 14400], index=1)
prefer_new = st.sidebar.checkbox(t("prefer_new"), value=True)
focus = st.sidebar.checkbox(t("focus"), value=False)
force_refresh = st.sidebar.checkbox(t("force_refresh"), value=True)
half_life_hours = st.sidebar.slider(t("half_life"), 2.0, 24.0, 6.0, 0.5)

snapshot = st.sidebar.checkbox(t("snapshot"), value=True)
snapshot_tag = st.sidebar.text_input(t("snapshot_tag"), value="premarket")

st.sidebar.markdown(f"### {t('thresholds')}")
mentions_min = st.sidebar.slider("Mentions min", 1, 10, 2)
swing_min = st.sidebar.slider("Swing min", 0, 80, 18)
pump_max_for_swing = st.sidebar.slider("Pump max (for swing)", 0, 80, 18)
insider_min_for_swing = st.sidebar.slider("Insider min (for swing)", 0, 10, 1)
pump_min = st.sidebar.slider("Pump min", 0, 120, 25)
insider_max_for_pump = st.sidebar.slider("Insider max (for pump)", 0, 10, 1)

if st.sidebar.button(t("run"), use_container_width=True):
    with st.spinner("Scraping + scoring..."):
        proc = run_scrape(
            force_refresh=force_refresh, cache_ttl=cache_ttl, focus=focus, prefer_new=prefer_new,
            half_life_hours=half_life_hours,
            snapshot=snapshot, snapshot_tag=snapshot_tag,
            swing_min=swing_min, pump_min=pump_min, mentions_min=mentions_min,
            pump_max_for_swing=pump_max_for_swing, insider_min_for_swing=insider_min_for_swing,
            insider_max_for_pump=insider_max_for_pump
        )
    st.sidebar.success("OK ✅")
    with st.sidebar.expander("Logs"):
        if proc.stdout:
            st.code(proc.stdout[-6000:])
        if proc.stderr:
            st.code(proc.stderr[-6000:])
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader(t("auto_refresh"))
auto_ui = st.sidebar.checkbox(t("auto_ui"), value=False)
auto_every = st.sidebar.selectbox(t("interval"), [30, 60, 120, 300], index=1)

now = datetime.now()
market_open = (now.weekday() < 5) and (9 <= now.hour <= 16)
if auto_ui and market_open and st_autorefresh is not None:
    st_autorefresh(interval=auto_every * 1000, key="ui_autorefresh")

# Guard
if not (os.path.exists(SUMMARY_CSV) and os.path.exists(WATCHLIST_CSV)):
    st.error(t("missing"))
    st.stop()

summary = load_csv(SUMMARY_CSV)
watchlist = load_csv(WATCHLIST_CSV)
details = load_details()
swing_df = load_csv(SWING_CSV) if os.path.exists(SWING_CSV) else pd.DataFrame()
pump_df = load_csv(PUMP_CSV) if os.path.exists(PUMP_CSV) else pd.DataFrame()

st.caption(
    f"🗓️ {t('updated')}: summary={file_mtime_str(SUMMARY_CSV)} | "
    f"watchlist={file_mtime_str(WATCHLIST_CSV)} | "
    f"swing={file_mtime_str(SWING_CSV)} | pump={file_mtime_str(PUMP_CSV)}"
)

# Metrics
dup_total = int(summary["Duplicates_Skipped"].sum()) if "Duplicates_Skipped" in summary.columns else 0
colA, colB, colC, colD, colE, colF = st.columns(6)
colA.metric("Net Global", f"{summary['Net_Sentiment'].sum():+d}")
colB.metric("Insider Total", f"{summary['Insider_Buy'].sum():d}")
colC.metric("Hype Total", f"{summary['Hype_Total'].sum():d}")
colD.metric("Dup skipped", f"{dup_total:d}")
colE.metric("Top Swing Sub", summary.sort_values("Swing_Score", ascending=False).iloc[0]["Subreddit"])
colF.metric("Top Pump Sub", summary.sort_values("Pump_Score", ascending=False).iloc[0]["Subreddit"])

# Tabs
tabs = t("tabs")
tab0, tab1, tab2, tabH, tab3, tab4 = st.tabs(tabs)

def show_list(df: pd.DataFrame, title: str, download_label: str, filename: str):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No rows for these thresholds.")
        return

    cols = [c for c in [
        "Ticker","Mentions","Weight_Sum","Net_Sentiment","Insider_Buy","Hype_Total",
        "Swing_Score","Pump_Score","Trade_Style","Rationale","Top_Subreddits"
    ] if c in df.columns]

    st.dataframe(df[cols].head(30), use_container_width=True)

    tickers = df["Ticker"].head(15).tolist()
    st.text_area(t("copy"), ", ".join(tickers), height=70)

    st.download_button(
        download_label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )

    st.markdown(f"**{t('links')}**")
    for ticker in tickers:
        st.markdown(f"- **${ticker}** — [TradingView]({tv_link(ticker)}) • [Yahoo]({yahoo_link(ticker)})")

with tab0:
    st.subheader("Premarket shortlist")
    left, right = st.columns(2)
    with left:
        show_list(swing_df, t("swing"), t("download_swing"), "reddit_watchlist_swing.csv")
    with right:
        show_list(pump_df, t("pump"), t("download_pump"), "reddit_watchlist_pump.csv")

with tab1:
    st.subheader("Subreddits overview (weighted)")
    cols = [c for c in [
        "Subreddit","Net_Sentiment","Insider_Buy","Hype_Total","Swing_Score","Pump_Score",
        "Trade_Style","Rationale","Duplicates_Skipped","Top_Tickers","Posts_Analyzed","HalfLifeHours","Scraped_At"
    ] if c in summary.columns]
    st.dataframe(summary[cols].sort_values(["Swing_Score","Pump_Score","Net_Sentiment"], ascending=False), use_container_width=True)

with tab2:
    st.subheader("Full watchlist (ticker-level, weighted)")
    query = st.text_input("Search ticker", "").strip().upper()
    wl = watchlist.copy()
    if query:
        wl = wl[wl["Ticker"].str.contains(query)]
    wl = wl.sort_values(["Pump_Score","Mentions"], ascending=False)

    st.bar_chart(wl.set_index("Ticker")["Mentions"].head(20))
    st.dataframe(wl.head(120), use_container_width=True)

with tabH:
    st.subheader(t("history_title"))

    snap_root = Path(SNAP_DIR)
    if not snap_root.exists():
        st.info("No snapshots yet. Enable 'Save snapshot' and run a scan.")
    else:
        # list snapshots as "YYYY-MM-DD/tag"
        items = []
        for day_dir in sorted([p for p in snap_root.iterdir() if p.is_dir()], reverse=True):
            for tag_dir in sorted([p for p in day_dir.iterdir() if p.is_dir()]):
                items.append(f"{day_dir.name}/{tag_dir.name}")

        if not items:
            st.info("No snapshots found.")
        else:
            pick = st.selectbox(t("pick_snap"), items, index=0)
            compare = st.selectbox(t("compare_with"), ["(none)"] + items, index=0)

            def load_snap_watchlist(key: str) -> pd.DataFrame:
                p = snap_root / key / "reddit_watchlist.csv"
                if not p.exists():
                    return pd.DataFrame()
                return pd.read_csv(p)

            dfA = load_snap_watchlist(pick)
            if dfA.empty:
                st.warning("Snapshot missing reddit_watchlist.csv")
            else:
                st.markdown("**Selected snapshot watchlist (top 50)**")
                st.dataframe(dfA.sort_values(["Pump_Score","Mentions"], ascending=False).head(50), use_container_width=True)

            if compare != "(none)":
                dfB = load_snap_watchlist(compare)
                if not dfA.empty and not dfB.empty:
                    setA = set(dfA["Ticker"].astype(str).str.upper())
                    setB = set(dfB["Ticker"].astype(str).str.upper())
                    added = sorted(list(setA - setB))
                    removed = sorted(list(setB - setA))
                    unchanged = sorted(list(setA & setB))

                    c1, c2, c3 = st.columns(3)
                    c1.metric(t("added"), len(added))
                    c2.metric(t("removed"), len(removed))
                    c3.metric(t("unchanged"), len(unchanged))

                    st.markdown("**Added (new today)**")
                    st.write(", ".join(added[:60]) if added else "-")

                    st.markdown("**Removed (yesterday only)**")
                    st.write(", ".join(removed[:60]) if removed else "-")

with tab3:
    st.subheader("Detailed posts (JSON)")
    if not details:
        st.info("JSON not found. Run scan.")
    else:
        subs = [d.get("subreddit", "") for d in details]
        chosen = st.selectbox("Subreddit", options=subs, index=0)
        min_conf = st.slider("Min confidence", 0, 10, 1)
        only_insider = st.checkbox("Insider only", False)

        block = next((d for d in details if d.get("subreddit") == chosen), None)
        if not block:
            st.warning("No data.")
        else:
            posts = block.get("posts", [])
            if only_insider:
                posts = [p for p in posts if int(p.get("score", {}).get("insider_buy", 0) or 0) > 0]
            posts = [p for p in posts if int(p.get("confidence", 0) or 0) >= min_conf]

            for p in posts[:80]:
                title = p.get("title", "")
                sig = p.get("signal", "")
                conf = int(p.get("confidence", 0) or 0)
                hs = int(p.get("hype_score", 0) or 0)
                wt = p.get("weight_total", 1.0)
                tickers = ", ".join(p.get("tickers", []))
                link = p.get("permalink", "")

                with st.expander(f"[{sig}] conf={conf} hype={hs} w={wt} — {title}"):
                    st.write(f"Tickers: {tickers if tickers else '-'}")
                    if link:
                        st.markdown(f"[Open Reddit post]({link})")

with tab4:
    st.subheader("Guide (quick)")
    st.write("1) Run scan 30–60 min before US open (Prefer NEW).")
    st.write("2) Use Swing list as main shortlist; Pump list as watch-only.")
    st.write("3) Validate on TradingView: trend, structure, levels, volume, invalidation.")
    st.write("4) Snapshot lets you track changes day-to-day (History tab).")
