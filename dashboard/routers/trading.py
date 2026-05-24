"""
Router: journal de trading et performance.
Couvre: trades CRUD (post/get/put/delete), performance, performance/advanced.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from analysis.technical_indicators import clean_for_json
from database.models import (
    save_trade, get_all_trades, get_trade_by_id,
    close_trade, delete_trade, DB_PATH,
)

router = APIRouter()


@router.post("/trades")
async def create_trade(request: Request):
    """Cree un nouveau trade OPEN avec champs disciplinaires optionnels.

    Requis : ticker, entry_price, stop_price, target_price, shares.
    Optionnels : setup_type, direction, notes, score_at_entry, market_regime.
    Pre-trade : thesis, conviction_pct (0-100), invalidation,
                tilt (1-5), process_score (1-10).
    Gate : gate_verdict, rules_violated.
    Retourne 400 si conviction_pct/tilt/process_score hors bornes.
    """
    try:
        body = await request.json()
        required = ("ticker", "entry_price", "stop_price", "target_price", "shares")
        missing = [f for f in required if f not in body]
        if missing:
            return clean_for_json({"error": f"Champs manquants : {', '.join(missing)}"})

        violations = []
        cv = body.get("conviction_pct")
        if cv is not None and not (0 <= int(cv) <= 100):
            violations.append(f"conviction_pct={cv} hors [0, 100]")
        tl = body.get("tilt")
        if tl is not None and not (1 <= int(tl) <= 5):
            violations.append(f"tilt={tl} hors [1, 5]")
        ps = body.get("process_score")
        if ps is not None and not (1 <= int(ps) <= 10):
            violations.append(f"process_score={ps} hors [1, 10]")
        if violations:
            return clean_for_json({"error": "Bornes invalides", "violations": violations})

        print(f"[Journal] Nouveau trade: {body.get(chr(39)+"ticker"+chr(39))} "
              f"gate={body.get(chr(39)+"gate_verdict"+chr(39))} conviction={cv} tilt={tl} process={ps}")

        trade_id = save_trade(body)
        trade = get_trade_by_id(trade_id)
        return clean_for_json({"id": trade_id, "trade": trade})
    except Exception as e:
        return clean_for_json({"error": str(e)})



@router.get("/trades")
def list_trades(status: str = None, limit: int = 100):
    """Liste tous les trades triés par date décroissante.
    Params optionnels : status (OPEN/CLOSED_WIN/CLOSED_LOSS/CLOSED_BE), limit.
    """
    try:
        trades = get_all_trades(limit=limit, status=status)

        total_closed = 0
        try:
            import sqlite3 as _sql3
            with _sql3.connect(DB_PATH) as _c:
                _row = _c.execute(
                    "SELECT COUNT(*) FROM trades WHERE status IN ('CLOSED_WIN','CLOSED_LOSS','CLOSED_BE')"
                ).fetchone()
                total_closed = _row[0] if _row else 0
        except Exception:
            pass

        return clean_for_json({
            "count":        len(trades),
            "trades":       trades,
            "total_closed": total_closed,
        })
    except Exception as e:
        return {"error": str(e), "trades": []}


@router.get("/trades/{trade_id}")
def get_trade(trade_id: int):
    """Retourne un trade par son id."""
    try:
        trade = get_trade_by_id(trade_id)
        if trade is None:
            return {"error": f"Trade {trade_id} introuvable"}
        return clean_for_json({"trade": trade})
    except Exception as e:
        return {"error": str(e)}


@router.put("/trades/{trade_id}/close")
async def close_trade_endpoint(trade_id: int, request: Request):
    """Cloture un trade.

    Requis : close_price.
    Optionnels : notes, initial_stop_violated (0/1), held_overnight (0/1),
                 rr_realized (float, override calcul auto).
    """
    try:
        body = await request.json()
        if "close_price" not in body:
            return clean_for_json({"error": "close_price requis"})
        rr_ov = body.get("rr_realized")
        trade = close_trade(
            trade_id,
            float(body["close_price"]),
            notes=body.get("notes"),
            initial_stop_violated=body.get("initial_stop_violated"),
            rr_realized_override=float(rr_ov) if rr_ov is not None else None,
            held_overnight=body.get("held_overnight"),
        )
        if trade is None:
            return clean_for_json({"error": f"Trade {trade_id} introuvable"})
        return clean_for_json({"trade": trade})
    except Exception as e:
        return clean_for_json({"error": str(e)})


@router.delete("/trades/{trade_id}")
def delete_trade_endpoint(trade_id: int):
    """Supprime un trade définitivement."""
    try:
        ok = delete_trade(trade_id)
        if not ok:
            return {"error": f"Trade {trade_id} introuvable"}
        return {"deleted": True, "id": trade_id}
    except Exception as e:
        return {"error": str(e)}


@router.get("/discipline/report")
def get_discipline_report():
    """Rapport disciplinaire (Kahneman/Duke) sur les trades clos.

    Metriques : override_rate, avg_R override vs conforming, tilt par niveau,
    stop_violation_rate, avg_rr_ratio (disposition effect),
    resulting_matrix (process x issue), overnight_rate.
    """
    _empty = {
        "n_trades": 0, "message": "Aucun trade clos.",
        "override_rate": None, "avg_r_override": None, "avg_r_conforming": None,
        "avg_tilt": None, "tilt_by_level": {},
        "stop_violation_rate": None, "avg_rr_ratio": None,
        "resulting_matrix": {
            "process_haut_gagnant": 0, "process_haut_perdant": 0,
            "process_bas_gagnant": 0,  "process_bas_perdant": 0,
        },
        "overnight_rate": None,
    }
    try:
        import sqlite3 as _sq
        with _sq.connect(DB_PATH) as conn:
            conn.row_factory = _sq.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status != 'OPEN' ORDER BY date_close ASC"
            ).fetchall()
        trades = [dict(r) for r in rows]
        if not trades:
            return clean_for_json(_empty)

        n = len(trades)

        def _avg_r(subset):
            vals = [t["rr_realized"] for t in subset if t.get("rr_realized") is not None]
            return round(sum(vals) / len(vals), 3) if vals else None

        overridden = [t for t in trades if t.get("gate_overridden")]
        conforming = [t for t in trades if not t.get("gate_overridden")]
        override_rate = round(len(overridden) / n * 100, 1)

        tilt_vals = [t.get("tilt") for t in trades if t.get("tilt") is not None]
        avg_tilt = round(sum(tilt_vals) / len(tilt_vals), 2) if tilt_vals else None
        tilt_by_level = {}
        for lvl in range(1, 6):
            sub = [t for t in trades if t.get("tilt") == lvl]
            tilt_by_level[str(lvl)] = {"n": len(sub), "avg_r": _avg_r(sub)}

        stop_violated = [t for t in trades if t.get("initial_stop_violated")]
        stop_violation_rate = round(len(stop_violated) / n * 100, 1)

        ratio_vals = [
            t["rr_realized"] / t["rr_planned"]
            for t in trades
            if t.get("rr_realized") is not None
            and t.get("rr_planned") and t["rr_planned"] > 0
        ]
        avg_rr_ratio = round(sum(ratio_vals) / len(ratio_vals), 3) if ratio_vals else None

        PROCESS_SEUIL = 6
        matrix = {"process_haut_gagnant": 0, "process_haut_perdant": 0,
                  "process_bas_gagnant": 0,  "process_bas_perdant": 0}
        for t in trades:
            ps = t.get("process_score")
            if ps is None:
                continue
            haut = ps >= PROCESS_SEUIL
            win  = t["status"] == "CLOSED_WIN"
            if haut and win:       matrix["process_haut_gagnant"] += 1
            elif haut and not win: matrix["process_haut_perdant"] += 1
            elif not haut and win: matrix["process_bas_gagnant"]  += 1
            else:                  matrix["process_bas_perdant"]  += 1

        overnight = [t for t in trades if t.get("held_overnight")]
        overnight_rate = round(len(overnight) / n * 100, 1)

        print(f"[Journal] discipline/report: {n} trades | override={override_rate}% | stop_viol={stop_violation_rate}%")

        return clean_for_json({
            "n_trades":            n,
            "override_rate":       override_rate,
            "avg_r_override":      _avg_r(overridden),
            "avg_r_conforming":    _avg_r(conforming),
            "avg_tilt":            avg_tilt,
            "tilt_by_level":       tilt_by_level,
            "stop_violation_rate": stop_violation_rate,
            "avg_rr_ratio":        avg_rr_ratio,
            "resulting_matrix":    matrix,
            "overnight_rate":      overnight_rate,
        })
    except Exception as e:
        return clean_for_json(dict(_empty, error=str(e)))


@router.get("/performance")
def get_performance():
    """Stats de performance complètes sur tous les trades clôturés."""
    _empty = {
        "total_trades": 0, "wins": 0, "losses": 0, "be": 0,
        "winrate": 0, "profit_factor": None, "expectancy": 0,
        "max_drawdown": 0, "total_pnl": 0, "avg_rr_realized": None,
        "best_trade": None, "worst_trade": None,
        "equity_curve": [], "monthly_returns": [], "drawdown_curve": [],
        "by_ticker": [], "by_setup": [], "by_regime": [],
    }
    try:
        import sqlite3 as _sq
        with _sq.connect(DB_PATH) as conn:
            conn.row_factory = _sq.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status != 'OPEN' ORDER BY date_close ASC"
            ).fetchall()
        trades = [dict(r) for r in rows]

        if not trades:
            return clean_for_json(_empty)

        wins   = [t for t in trades if t["status"] == "CLOSED_WIN"]
        losses = [t for t in trades if t["status"] == "CLOSED_LOSS"]
        be     = [t for t in trades if t["status"] == "CLOSED_BE"]

        total_pnl     = sum(t["pnl_dollars"] or 0 for t in trades)
        gross_win     = sum(t["pnl_dollars"] or 0 for t in wins)
        gross_loss    = abs(sum(t["pnl_dollars"] or 0 for t in losses))
        winrate       = round(len(wins) / len(trades) * 100, 1)
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
        expectancy    = round(total_pnl / len(trades), 2)

        rr_vals = [t["rr_realized"] for t in trades if t.get("rr_realized") is not None]
        avg_rr  = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None

        by_pnl      = sorted(trades, key=lambda t: t["pnl_dollars"] or 0)
        best_trade  = {"ticker": by_pnl[-1]["ticker"], "pnl": by_pnl[-1]["pnl_dollars"], "date": (by_pnl[-1]["date_close"] or "")[:10]} if by_pnl else None
        worst_trade = {"ticker": by_pnl[0]["ticker"],  "pnl": by_pnl[0]["pnl_dollars"],  "date": (by_pnl[0]["date_close"] or "")[:10]}  if by_pnl else None

        cum = 0.0
        peak = 0.0
        equity_curve   = []
        drawdown_curve = []
        for t in trades:
            cum  += t["pnl_dollars"] or 0
            date  = (t["date_close"] or t["date_open"] or "")[:10]
            equity_curve.append({"date": date, "pnl": round(cum, 2)})
            peak  = max(peak, cum)
            drawdown_curve.append({"date": date, "drawdown": round(cum - peak, 2)})

        max_drawdown = min((d["drawdown"] for d in drawdown_curve), default=0)

        monthly: dict = {}
        for t in trades:
            date  = (t["date_close"] or t["date_open"] or "")[:10]
            month = date[:7]
            if month not in monthly:
                monthly[month] = {"month": month, "pnl": 0.0, "trades": 0, "wins": 0}
            monthly[month]["pnl"]    += t["pnl_dollars"] or 0
            monthly[month]["trades"] += 1
            if t["status"] == "CLOSED_WIN":
                monthly[month]["wins"] += 1
        monthly_returns = [
            {
                "month":   v["month"],
                "pnl":     round(v["pnl"], 2),
                "trades":  v["trades"],
                "winrate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0,
            }
            for v in sorted(monthly.values(), key=lambda x: x["month"])
        ]

        def _group(trades_list, key_fn, val_fn):
            m: dict = {}
            for t in trades_list:
                k = key_fn(t)
                if k not in m:
                    m[k] = {"_wins": 0, "_trades": 0, "_pnl": 0.0, "_gw": 0.0, "_gl": 0.0, "_rr": [], "_key": k}
                m[k]["_trades"] += 1
                m[k]["_pnl"]    += t["pnl_dollars"] or 0
                pnl = t["pnl_dollars"] or 0
                if pnl > 0: m[k]["_gw"] += pnl
                else:       m[k]["_gl"] += abs(pnl)
                if t["status"] == "CLOSED_WIN": m[k]["_wins"] += 1
                if t.get("rr_realized") is not None: m[k]["_rr"].append(t["rr_realized"])
            return {k: val_fn(v) for k, v in m.items()}

        tk_map = _group(
            trades,
            lambda t: t["ticker"],
            lambda v: {
                "ticker":  v["_key"],
                "trades":  v["_trades"],
                "winrate": round(v["_wins"] / v["_trades"] * 100, 1),
                "pnl":     round(v["_pnl"], 2),
                "avg_rr":  round(sum(v["_rr"]) / len(v["_rr"]), 2) if v["_rr"] else None,
            }
        )
        by_ticker = sorted(tk_map.values(), key=lambda x: x["pnl"], reverse=True)

        st_map = _group(
            trades,
            lambda t: t.get("setup_type") or "MANUAL",
            lambda v: {
                "type":          v["_key"],
                "trades":        v["_trades"],
                "winrate":       round(v["_wins"] / v["_trades"] * 100, 1),
                "pnl":           round(v["_pnl"], 2),
                "profit_factor": round(v["_gw"] / v["_gl"], 2) if v["_gl"] > 0 else None,
            }
        )
        by_setup = sorted(st_map.values(), key=lambda x: x["pnl"], reverse=True)

        rg_map = _group(
            trades,
            lambda t: t.get("market_regime") or "N/A",
            lambda v: {
                "regime":  v["_key"],
                "trades":  v["_trades"],
                "winrate": round(v["_wins"] / v["_trades"] * 100, 1),
                "pnl":     round(v["_pnl"], 2),
            }
        )
        by_regime = sorted(rg_map.values(), key=lambda x: x["pnl"], reverse=True)

        return clean_for_json({
            "total_trades":    len(trades),
            "wins":            len(wins),
            "losses":          len(losses),
            "be":              len(be),
            "winrate":         winrate,
            "profit_factor":   profit_factor,
            "expectancy":      expectancy,
            "max_drawdown":    round(max_drawdown, 2),
            "total_pnl":       round(total_pnl, 2),
            "avg_rr_realized": avg_rr,
            "best_trade":      best_trade,
            "worst_trade":     worst_trade,
            "equity_curve":    equity_curve,
            "monthly_returns": monthly_returns,
            "drawdown_curve":  drawdown_curve,
            "by_ticker":       by_ticker,
            "by_setup":        by_setup,
            "by_regime":       by_regime,
        })
    except Exception as e:
        return clean_for_json(dict(_empty, error=str(e)))


@router.get("/performance/advanced")
def get_performance_advanced():
    """
    Métriques avancées : Sharpe, Sortino, Calmar, Kelly, Monte Carlo.
    Monte Carlo est lent (1-3s) — appelé manuellement depuis le dashboard.
    """
    _empty_adv = {
        "n_trades": 0,
        "sharpe_ratio": None, "sortino_ratio": None, "calmar_ratio": None,
        "expectancy": {}, "kelly_criterion": None, "profit_factor": None,
        "max_consecutive_wins": None, "max_consecutive_losses": None,
        "monte_carlo": None, "r_distribution": {},
        "message": "Pas encore de trades clotures.",
    }
    try:
        import sqlite3 as _sq
        from analysis.advanced_metrics import calculate_all_advanced_metrics

        with _sq.connect(DB_PATH) as conn:
            conn.row_factory = _sq.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status != 'OPEN' ORDER BY date_close ASC"
            ).fetchall()
        trades = [dict(r) for r in rows]

        if not trades:
            return clean_for_json(_empty_adv)

        result = calculate_all_advanced_metrics(trades)

        n = result["n_trades"]
        if n < 20:
            result["message"] = (
                f"{n} trade(s) cloture(s). "
                "Accumule 10+ pour Sharpe/Sortino/Calmar, 20+ pour Monte Carlo."
            )
        else:
            result["message"] = None

        return clean_for_json(result)
    except Exception as e:
        return clean_for_json(dict(_empty_adv, error=str(e)))
