"""
Agent_Trader — Flask API
Reads pre-computed JSON files written by Mac harvest.
Makes ZERO external network calls. All data comes from local JSON.
"""
import json
import os
from pathlib import Path
from functools import wraps
from flask import Flask, jsonify, request

from config import (
    FLASK_SECRET_KEY, USER_EMAIL,
    RESULTS_JSON, SNAPSHOT_JSON, METADATA_JSON, NEWS_JSON,
    DB_PATH, TOKEN_PREFIX, generate_token, validate_token
)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict | list | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _require_token(f):
    """Decorator — validate at_* token in query string or Authorization header."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = (request.args.get("token") or
                 request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
        if not token or not validate_token(token):
            return jsonify({"error": "unauthorised", "hint": "POST /api/auth/verify to get your token"}), 401
        return f(*args, **kwargs)
    return wrapper


# ── Public Endpoints ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "app": "Agent_Trader",
        "version": "1.0.0",
        "status": "ok",
        "docs": "/api/status",
    })


@app.route("/api/status")
def status():
    meta = _load_json(METADATA_JSON)
    return jsonify({
        "status": "ok",
        "app": "Agent_Trader",
        "version": "1.0.0",
        "configured": bool(USER_EMAIL),
        "db_exists": os.path.exists(DB_PATH),
        "snapshot_exists": os.path.exists(SNAPSHOT_JSON),
        "last_harvest": meta.get("generated_at") if meta else None,
        "last_run_id":  meta.get("run_id")        if meta else None,
        "stocks_with_prices": meta.get("stocks_with_prices") if meta else 0,
    })


@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    """Given an email, return the token if it matches USER_EMAIL."""
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or request.form.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400
    configured = USER_EMAIL.strip().lower()
    if email != configured:
        return jsonify({"error": "email not recognised"}), 403
    try:
        token = generate_token(USER_EMAIL)
        return jsonify({"token": token, "prefix": TOKEN_PREFIX, "email": email})
    except ValueError as e:
        return jsonify({"error": str(e), "hint": "Set SECRET_SALT in .env"}), 500


# ── Protected Endpoints ────────────────────────────────────────────────────────

@app.route("/api/metadata")
@_require_token
def metadata():
    meta = _load_json(METADATA_JSON)
    if not meta:
        return jsonify({"error": "metadata.json not found — harvest not run yet"}), 404
    return jsonify(meta)


@app.route("/api/snapshot")
@_require_token
def snapshot():
    """All 50 stocks analytics snapshot."""
    data = _load_json(SNAPSHOT_JSON)
    if not data:
        return jsonify({"error": "snapshot.json not found — run harvest first"}), 404

    # Optional filters
    sector  = request.args.get("sector")
    min_rsi = request.args.get("min_rsi", type=float)
    max_rsi = request.args.get("max_rsi", type=float)
    macd    = request.args.get("macd")    # bullish | bearish | neutral
    sort_by = request.args.get("sort", "ret_1y")

    stocks = data.get("stocks", [])
    if sector:
        stocks = [s for s in stocks if (s.get("sector") or "").lower() == sector.lower()]
    if min_rsi is not None:
        stocks = [s for s in stocks if s.get("rsi") is not None and s["rsi"] >= min_rsi]
    if max_rsi is not None:
        stocks = [s for s in stocks if s.get("rsi") is not None and s["rsi"] <= max_rsi]
    if macd:
        stocks = [s for s in stocks if s.get("macd") == macd]

    # Sort
    reverse = True
    if sort_by.startswith("-"):
        sort_by = sort_by[1:]
        reverse = False
    stocks = sorted(stocks, key=lambda s: (s.get(sort_by) is None, s.get(sort_by) or 0),
                    reverse=reverse)

    return jsonify({
        "generated_at": data.get("generated_at"),
        "count": len(stocks),
        "stocks": stocks,
    })


@app.route("/api/portfolio")
@_require_token
def portfolio():
    """Portfolio holdings with live P&L from latest prices."""
    data = _load_json(RESULTS_JSON)
    if not data:
        return jsonify({"holdings": [], "total_invested": 0,
                        "total_current": 0, "total_upnl": 0, "hint": "Upload portfolio first"})

    holdings = data.get("holdings", [])
    total_inv = sum(h.get("invested") or 0 for h in holdings)
    total_cur = sum(h.get("current") or 0 for h in holdings)
    total_upnl = total_cur - total_inv

    return jsonify({
        "generated_at":  data.get("generated_at"),
        "count":         len(holdings),
        "total_invested": round(total_inv, 2),
        "total_current":  round(total_cur, 2),
        "total_upnl":     round(total_upnl, 2),
        "total_pnl_pct":  round(total_upnl / total_inv * 100, 2) if total_inv else 0,
        "holdings":       holdings,
    })


@app.route("/api/news")
@_require_token
def news():
    """Recent news from RSS feeds."""
    data = _load_json(NEWS_JSON)
    if not data:
        return jsonify({"items": [], "count": 0})

    items   = data.get("items", [])
    ticker  = request.args.get("ticker")
    cat     = request.args.get("category")
    limit   = request.args.get("limit", 50, type=int)

    if ticker:
        items = [n for n in items if ticker in (n.get("tickers_mentioned") or [])]
    if cat:
        items = [n for n in items if n.get("category") == cat.upper()]

    return jsonify({
        "generated_at": data.get("generated_at"),
        "count": len(items),
        "items": items[:limit],
    })


@app.route("/api/stock/<ticker>")
@_require_token
def stock_detail(ticker: str):
    """Detailed analytics for a single stock."""
    ticker = ticker.upper()
    snap   = _load_json(SNAPSHOT_JSON)
    if not snap:
        return jsonify({"error": "No data"}), 404

    match = next((s for s in snap.get("stocks", []) if s["ticker"] == ticker), None)
    if not match:
        return jsonify({"error": f"{ticker} not found in snapshot"}), 404

    # Attach relevant news
    news_data = _load_json(NEWS_JSON)
    related_news = []
    if news_data:
        related_news = [
            n for n in news_data.get("items", [])
            if ticker in (n.get("tickers_mentioned") or [])
        ][:10]

    return jsonify({**match, "recent_news": related_news})


@app.route("/api/sectors")
@_require_token
def sectors():
    """Sector-level aggregated analytics."""
    snap = _load_json(SNAPSHOT_JSON)
    if not snap:
        return jsonify({"sectors": []})

    from collections import defaultdict
    sector_map = defaultdict(list)
    for s in snap.get("stocks", []):
        sector_map[s.get("sector", "Unknown")].append(s)

    result = []
    for sec, stocks in sorted(sector_map.items()):
        rets = [s["ret_1y"] for s in stocks if s.get("ret_1y") is not None]
        betas = [s["beta_1y"] for s in stocks if s.get("beta_1y") is not None]
        result.append({
            "sector":      sec,
            "count":       len(stocks),
            "avg_ret_1y":  round(sum(rets)  / len(rets),  2) if rets  else None,
            "avg_beta":    round(sum(betas) / len(betas), 2) if betas else None,
            "stocks":      [s["ticker"] for s in stocks],
        })

    return jsonify({"generated_at": snap.get("generated_at"), "sectors": result})


@app.route("/api/portfolio/upload", methods=["POST"])
@_require_token
def portfolio_upload():
    """
    Accept portfolio CSV upload.
    Expects JSON body: {"holdings": [{"ticker":"HDFCBANK","qty":10,"avg_cost":1600}, ...]}
    """
    data = request.get_json(silent=True) or {}
    holdings = data.get("holdings", [])
    if not holdings:
        return jsonify({"error": "holdings array is required"}), 400

    snap = _load_json(SNAPSHOT_JSON) or {}
    known = {s["ticker"] for s in snap.get("stocks", [])}

    valid        = []
    unrecognised = []

    for h in holdings:
        ticker  = str(h.get("ticker", "")).upper().strip()
        qty     = h.get("qty") or h.get("quantity")
        cost    = h.get("avg_cost") or h.get("cost")
        if not ticker or qty is None or cost is None:
            continue
        if ticker in known:
            valid.append({"ticker": ticker, "qty": float(qty), "avg_cost": float(cost)})
        else:
            unrecognised.append(ticker)

    if not valid:
        return jsonify({
            "error": "No valid holdings found",
            "unrecognised": unrecognised,
            "hint": "Tickers must match Nifty50 symbols e.g. HDFCBANK, TCS, INFY",
        }), 422

    # Write confirmed holdings to results.json in-place
    # (DB update happens on next Mac harvest — PA only updates the JSON)
    try:
        snap_stocks = {s["ticker"]: s for s in snap.get("stocks", [])}
        result_holdings = []
        for h in valid:
            t   = h["ticker"]
            s   = snap_stocks.get(t, {})
            cmp = s.get("price") or 0
            inv = h["qty"] * h["avg_cost"]
            cur = h["qty"] * cmp
            result_holdings.append({
                "ticker":   t,
                "name":     s.get("name", t),
                "qty":      h["qty"],
                "avg_cost": h["avg_cost"],
                "cmp":      cmp,
                "invested": round(inv, 2),
                "current":  round(cur, 2),
                "upnl":     round(cur - inv, 2),
                "pnl_pct":  round((cur - inv) / inv * 100, 2) if inv else 0,
                "ret_1y":   s.get("ret_1y"),
                "beta":     s.get("beta_1y"),
                "alpha":    s.get("alpha"),
                "rsi":      s.get("rsi"),
                "macd":     s.get("macd"),
                "sector":   s.get("sector"),
            })

        existing = _load_json(RESULTS_JSON) or {}
        existing["holdings"] = result_holdings
        existing["count"]    = len(result_holdings)
        existing["generated_at"] = __import__("datetime").datetime.now().isoformat()

        with open(RESULTS_JSON, "w") as f:
            json.dump(existing, f, indent=2)

    except Exception as e:
        return jsonify({"error": f"Failed to save holdings: {e}"}), 500

    return jsonify({
        "status":        "saved",
        "valid_count":   len(valid),
        "unrecognised":  unrecognised,
        "holdings":      valid,
        "note":          "Holdings will be enriched with latest analytics on next Mac harvest.",
    })


# ── Initialisation ─────────────────────────────────────────────────────────────

def _auto_init():
    """Create data directory and DB on first cold start."""
    from config import DATA_DIR
    os.makedirs(str(DATA_DIR), exist_ok=True)
    if not os.path.exists(DB_PATH):
        try:
            from tools.init_db import init_db
            init_db()
        except Exception as e:
            app.logger.warning(f"Auto-init DB failed: {e}")


_auto_init()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
