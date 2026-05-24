"""
Base de données SQLite — historique des scores et du contexte marché.
Fichier DB : database/trading_agent.db
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "trading_agent.db"


# ── Initialisation ──────────────────────────────────────────────────────────


# Colonnes disciplinaires ajoutees en v2 (migration idempotente)
_NEW_COLUMNS_V2: list[tuple[str, str]] = [
    ("thesis",                "TEXT"),
    ("conviction_pct",        "INTEGER"),
    ("invalidation",          "TEXT"),
    ("tilt",                  "INTEGER"),
    ("process_score",         "INTEGER"),
    ("gate_verdict",          "TEXT"),
    ("gate_overridden",       "INTEGER"),
    ("rules_violated",        "TEXT"),
    ("initial_stop_violated", "INTEGER"),
    ("held_overnight",        "INTEGER"),
]


def _migrate_trades_v2(db_path: Path = DB_PATH) -> None:
    """Migration idempotente : ajoute les colonnes disciplinaires v2 si absentes."""
    with sqlite3.connect(db_path) as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
        added: list[str] = []
        for col_name, col_type in _NEW_COLUMNS_V2:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
                added.append(col_name)
        if added:
            print(f"[Journal] Migration v2: colonnes ajoutees: {', '.join(added)}")
        else:
            print("[Journal] Migration v2: schema deja a jour")


def init_db(db_path: Path = DB_PATH) -> None:
    """Crée les tables si elles n'existent pas."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scores_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT NOT NULL,
                ticker        TEXT NOT NULL,
                total_score   INTEGER NOT NULL,
                sma200_score  INTEGER NOT NULL,
                volume_score  INTEGER NOT NULL,
                reddit_score  INTEGER NOT NULL,
                news_score    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS market_context_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                regime      TEXT NOT NULL,
                score       INTEGER NOT NULL,
                vix         REAL,
                spy_change  REAL,
                dxy         REAL
            );

            CREATE TABLE IF NOT EXISTS trades (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date_open        TEXT NOT NULL,
                date_close       TEXT,
                ticker           TEXT NOT NULL,
                direction        TEXT NOT NULL DEFAULT 'LONG',
                setup_type       TEXT NOT NULL DEFAULT 'MANUAL',
                entry_price      REAL NOT NULL,
                stop_price       REAL NOT NULL,
                target_price     REAL NOT NULL,
                close_price      REAL,
                shares           INTEGER NOT NULL,
                risk_dollars     REAL,
                risk_pct         REAL,
                rr_planned       REAL,
                rr_realized      REAL,
                pnl_dollars      REAL,
                status           TEXT NOT NULL DEFAULT 'OPEN',
                notes            TEXT,
                score_at_entry   INTEGER,
                market_regime    TEXT
            );
        """)
    _migrate_trades_v2(db_path)


# ── Écriture ────────────────────────────────────────────────────────────────

def save_scores(date: str, scores_list: list[dict], db_path: Path = DB_PATH) -> None:
    """
    Sauvegarde les scores de tous les tickers pour une date donnée.

    Paramètres
    ----------
    date        : "YYYY-MM-DD"
    scores_list : liste de dicts retournés par scoring.score_ticker()
    """
    rows = [
        (
            date,
            s["ticker"],
            s["total_score"],
            s["sma200_score"],
            s["volume_score"],
            s["reddit_score"],
            s["news_score"],
        )
        for s in scores_list
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO scores_history
                (date, ticker, total_score, sma200_score, volume_score, reddit_score, news_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def save_market_context(date: str, context_dict: dict, db_path: Path = DB_PATH) -> None:
    """
    Sauvegarde le contexte marché pour une date donnée.

    Paramètres
    ----------
    date         : "YYYY-MM-DD"
    context_dict : dict retourné par scoring.score_market_context()
    """
    details = context_dict.get("details", {})
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO market_context_history
                (date, regime, score, vix, spy_change, dxy)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                context_dict["regime"],
                context_dict["score"],
                details.get("vix"),
                details.get("spy_change"),
                details.get("dxy"),
            ),
        )


# ── Lecture ─────────────────────────────────────────────────────────────────

def get_score_history(ticker: str, days: int = 30, db_path: Path = DB_PATH) -> list[dict]:
    """
    Retourne l'historique des scores d'un ticker sur N jours.

    Retourne une liste de dicts triés du plus récent au plus ancien.
    """
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT date, total_score, sma200_score, volume_score, reddit_score, news_score
            FROM scores_history
            WHERE ticker = ? AND date >= ?
            ORDER BY date DESC
            """,
            (ticker, since),
        ).fetchall()
    return [dict(row) for row in rows]


def get_score_trend(ticker: str, days: int = 7, db_path: Path = DB_PATH) -> dict:
    """
    Retourne la tendance du score sur N jours.

    Retourne un dict avec :
        - trend   : "HAUSSE" / "BAISSE" / "STABLE"
        - delta   : variation du score (dernier - premier)
        - history : liste des (date, total_score)
    """
    history = get_score_history(ticker, days=days, db_path=db_path)

    if len(history) < 2:
        return {"trend": "STABLE", "delta": 0, "history": history}

    # history est trié du plus récent au plus ancien
    latest = history[0]["total_score"]
    oldest = history[-1]["total_score"]
    delta = latest - oldest

    if delta >= 5:
        trend = "HAUSSE"
    elif delta <= -5:
        trend = "BAISSE"
    else:
        trend = "STABLE"

    return {
        "trend": trend,
        "delta": delta,
        "history": [(row["date"], row["total_score"]) for row in history],
    }


# ── Journal de trading ──────────────────────────────────────────────────────

def save_trade(trade_dict: dict, db_path: Path = DB_PATH) -> int:
    """Enregistre un nouveau trade OPEN avec champs disciplinaires optionnels.

    Requis : ticker, entry_price, stop_price, target_price, shares.
    Pre-trade : thesis, conviction_pct (0-100), invalidation, tilt (1-5),
                process_score (1-10). Validation des bornes : faite cote API.
    Gate      : gate_verdict, rules_violated (liste ou JSON string).
    gate_overridden = 1 si gate_verdict != GO (ou GO-WARN / NO-GO).
    Retourne l id du trade cree.
    """
    entry  = float(trade_dict["entry_price"])
    stop   = float(trade_dict["stop_price"])
    target = float(trade_dict["target_price"])
    shares = int(trade_dict["shares"])

    risk_per_share = entry - stop
    risk_dollars   = round(risk_per_share * shares, 2) if risk_per_share > 0 else 0.0
    rr_planned     = round((target - entry) / risk_per_share, 2) if risk_per_share > 0 else 0.0
    date_open      = trade_dict.get("date_open", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Champs pre-trade disciplinaires
    thesis         = trade_dict.get("thesis")
    conviction_pct = trade_dict.get("conviction_pct")
    invalidation   = trade_dict.get("invalidation")
    tilt           = trade_dict.get("tilt")
    process_score  = trade_dict.get("process_score")

    # Champs gate
    gate_verdict    = trade_dict.get("gate_verdict")
    gate_overridden = trade_dict.get("gate_overridden", 1 if gate_verdict == "NO-GO" else 0)
    raw_violated    = trade_dict.get("rules_violated", [])
    if isinstance(raw_violated, list):
        rules_violated = json.dumps(raw_violated) if raw_violated else None
    else:
        rules_violated = raw_violated if raw_violated else None

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO trades
                (date_open, ticker, direction, setup_type, entry_price, stop_price,
                 target_price, shares, risk_dollars, risk_pct, rr_planned, status,
                 notes, score_at_entry, market_regime,
                 thesis, conviction_pct, invalidation, tilt, process_score,
                 gate_verdict, gate_overridden, rules_violated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_open,
                trade_dict["ticker"].upper(),
                trade_dict.get("direction", "LONG"),
                trade_dict.get("setup_type", "MANUAL"),
                entry, stop, target, shares,
                risk_dollars,
                trade_dict.get("risk_pct"),
                rr_planned,
                trade_dict.get("notes"),
                trade_dict.get("score_at_entry"),
                trade_dict.get("market_regime"),
                thesis, conviction_pct, invalidation, tilt, process_score,
                gate_verdict, gate_overridden, rules_violated,
            ),
        )
        return cursor.lastrowid



def update_trade(trade_id: int, updates: dict, db_path: Path = DB_PATH) -> None:
    """Met à jour les champs d'un trade existant."""
    _ALLOWED = {
        "date_open", "date_close", "ticker", "direction", "setup_type",
        "entry_price", "stop_price", "target_price", "close_price", "shares",
        "risk_dollars", "risk_pct", "rr_planned", "rr_realized", "pnl_dollars",
        "status", "notes", "score_at_entry", "market_regime",
        "thesis", "conviction_pct", "invalidation", "tilt", "process_score",
        "gate_verdict", "gate_overridden", "rules_violated",
        "initial_stop_violated", "held_overnight",
    }
    clean = {k: v for k, v in updates.items() if k in _ALLOWED}
    if not clean:
        return
    set_clause = ", ".join(f"{k} = ?" for k in clean)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE trades SET {set_clause} WHERE id = ?",
            list(clean.values()) + [trade_id],
        )


def close_trade(
    trade_id: int,
    close_price: float,
    notes: str | None = None,
    initial_stop_violated: int | None = None,
    rr_realized_override: float | None = None,
    held_overnight: int | None = None,
    db_path: Path = DB_PATH,
) -> dict | None:
    """Cloture un trade et calcule PnL, R:R realise et statut.

    Calcule automatiquement pnl_dollars, rr_realized (sauf si rr_realized_override
    fourni), et status (CLOSED_WIN/LOSS/BE).
    Stocke les champs disciplinaires post-trade si fournis :
      initial_stop_violated : 1 si le stop initial a ete modifie apres l entree
      held_overnight        : 1 si la position a ete maintenue hors session
      rr_realized_override  : remplace le R:R auto-calcule (ex. pour saisie manuelle)
    Retourne le trade mis a jour, ou None si introuvable.
    """
    trade = get_trade_by_id(trade_id, db_path=db_path)
    if trade is None:
        return None

    entry  = float(trade["entry_price"])
    stop   = float(trade["stop_price"])
    target = float(trade["target_price"])
    shares = int(trade["shares"])
    risk   = entry - stop

    pnl_dollars = round((close_price - entry) * shares, 2)
    rr_realized = (
        rr_realized_override
        if rr_realized_override is not None
        else (round((close_price - entry) / risk, 2) if risk != 0 else 0.0)
    )

    if close_price >= target:
        status = "CLOSED_WIN"
    elif close_price <= stop:
        status = "CLOSED_LOSS"
    elif risk != 0 and abs(close_price - entry) <= abs(risk) * 0.5:
        status = "CLOSED_BE"
    else:
        status = "CLOSED_WIN" if pnl_dollars > 0 else "CLOSED_LOSS"

    upd: dict = {
        "date_close":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "close_price": close_price,
        "pnl_dollars": pnl_dollars,
        "rr_realized": rr_realized,
        "status":      status,
    }
    if notes:
        upd["notes"] = notes
    if initial_stop_violated is not None:
        upd["initial_stop_violated"] = initial_stop_violated
    if held_overnight is not None:
        upd["held_overnight"] = held_overnight
    update_trade(trade_id, upd, db_path=db_path)
    return get_trade_by_id(trade_id, db_path=db_path)

def get_open_trades(db_path: Path = DB_PATH) -> list[dict]:
    """Retourne tous les trades avec status=OPEN, triés par date décroissante."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY date_open DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_trades(limit: int = 100, status: str | None = None,
                   db_path: Path = DB_PATH) -> list[dict]:
    """Retourne tous les trades, triés par date décroissante."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = ? ORDER BY date_open DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY date_open DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_trade_by_id(trade_id: int, db_path: Path = DB_PATH) -> dict | None:
    """Retourne un trade par son id, ou None s'il n'existe pas."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_trade(trade_id: int, db_path: Path = DB_PATH) -> bool:
    """Supprime un trade. Retourne True si un enregistrement a été supprimé."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    return cursor.rowcount > 0


# ── Test basique ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    # DB de test temporaire
    test_db = Path(__file__).parent / "test_trading_agent.db"
    if test_db.exists():
        test_db.unlink()

    print("=== Test database/models.py ===\n")

    init_db(test_db)
    print(f"[OK] DB créée : {test_db}")

    # Données de test — J-2
    scores_j2 = [
        {"ticker": "NVDA", "total_score": 62, "sma200_score": 22, "volume_score": 25, "reddit_score": 10, "news_score": 5},
        {"ticker": "AAPL", "total_score": 45, "sma200_score": 13, "volume_score": 5,  "reddit_score": 12, "news_score": 15},
        {"ticker": "PLTR", "total_score": 70, "sma200_score": 5,  "volume_score": 18, "reddit_score": 25, "news_score": 22},
    ]
    save_scores("2026-03-07", scores_j2, test_db)

    # Données de test — J-1
    scores_j1 = [
        {"ticker": "NVDA", "total_score": 68, "sma200_score": 22, "volume_score": 25, "reddit_score": 15, "news_score": 6},
        {"ticker": "AAPL", "total_score": 42, "sma200_score": 13, "volume_score": 5,  "reddit_score": 9,  "news_score": 15},
        {"ticker": "PLTR", "total_score": 65, "sma200_score": 5,  "volume_score": 18, "reddit_score": 20, "news_score": 22},
    ]
    save_scores("2026-03-08", scores_j1, test_db)

    # Données de test — aujourd'hui
    scores_today = [
        {"ticker": "NVDA", "total_score": 75, "sma200_score": 25, "volume_score": 25, "reddit_score": 15, "news_score": 10},
        {"ticker": "AAPL", "total_score": 38, "sma200_score": 13, "volume_score": 5,  "reddit_score": 5,  "news_score": 15},
        {"ticker": "PLTR", "total_score": 58, "sma200_score": 5,  "volume_score": 10, "reddit_score": 20, "news_score": 23},
    ]
    save_scores("2026-03-09", scores_today, test_db)
    print("[OK] Scores insérés (3 jours × 3 tickers)")

    context = {
        "regime": "NEUTRAL",
        "score": 52,
        "details": {"vix": 18.5, "spy_change": 0.3, "dxy": 103.2},
    }
    save_market_context("2026-03-09", context, test_db)
    print("[OK] Contexte marché inséré")

    # Lecture
    history = get_score_history("NVDA", days=30, db_path=test_db)
    print(f"\nHistorique NVDA ({len(history)} entrées) :")
    for row in history:
        print(f"  {row['date']} → score {row['total_score']}")

    trend = get_score_trend("NVDA", days=7, db_path=test_db)
    print(f"\nTendance NVDA : {trend['trend']} (delta={trend['delta']:+d})")

    trend_aapl = get_score_trend("AAPL", days=7, db_path=test_db)
    print(f"Tendance AAPL : {trend_aapl['trend']} (delta={trend_aapl['delta']:+d})")

    # Nettoyage
    test_db.unlink()
    print("\n[OK] models.py fonctionne correctement.")
